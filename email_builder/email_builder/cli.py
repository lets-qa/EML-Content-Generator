import argparse
import logging
import os
import sys
import random
import re
import mimetypes
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional

from email.message import EmailMessage
from email.utils import formatdate, make_msgid

# ----------------------------
# Profiles
# ----------------------------
PROFILE_DEFAULTS = {
    "mixed_business": {
        "html_pct": 88,
        "attach_pct": 25,
        "subject_len": 50,
        "num_emails": 1000,
        "output_dir": "output_emails/"
    },
    "internal_ops": {
        "html_pct": 75,
        "attach_pct": 15,
        "subject_len": 50,
        "num_emails": 1000,
        "output_dir": "output_emails/"
    },
    "marketing": {
        "html_pct": 98,
        "attach_pct": 2,
        "subject_len": 50,
        "num_emails": 1000,
        "output_dir": "output_emails/"
    }
}

ATTACH_COUNT_DIST: List[Tuple[int, float]] = [
    (1, 0.80),
    (2, 0.15),
    (3, 0.04),
    (4, 0.01),
]

# ----------------------------
# Logging
# ----------------------------
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

# ----------------------------
# CLI
# ----------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Email Builder Tool - Generate .eml files with configurable options"
    )

    # Profile selection
    parser.add_argument("--profile", choices=PROFILE_DEFAULTS.keys(), help="Predefined traffic profile")

    # Core inputs
    parser.add_argument("--to_list", required=True, help="Path to file with recipient emails")
    parser.add_argument("--from_list", required=True, help="Path to file with sender emails")
    parser.add_argument("--body_dir", required=True, help="Directory with plain text body samples")
    parser.add_argument("--html_dir", required=True, help="Directory with HTML content samples")
    parser.add_argument("--attach_dir", required=True, help="Directory with attachment files")
    parser.add_argument("--relay_hosts", required=True, help="Path to file with relay hostnames")

    # Configurable options
    parser.add_argument("--html_pct", type=int, help="Percentage of emails as HTML (0-100)")
    parser.add_argument("--attach_pct", type=int, help="Percentage of emails with attachments (0-100)")
    parser.add_argument("--subject_len", type=int, help="Number of chars from body for subject (>=1)")
    parser.add_argument("--num_emails", type=int, help="Number of emails to generate (>0)")
    parser.add_argument("--output_dir", help="Directory to save generated .eml files")

    # Engine behavior (optional)
    parser.add_argument("--selection_mode", choices=["random", "linear"], default="random",
                        help="How to select senders/recipients/content/attachments (default: random)")
    parser.add_argument("--max_attachments", type=int, default=4,
                        help="Upper cap on attachments per email (default: 4)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility (default: None)")

    # Date range randomization
    parser.add_argument("--date_start", help="Start date for randomized timestamps (YYYY-MM-DD, UTC)")
    parser.add_argument("--date_end", help="End date for randomized timestamps (YYYY-MM-DD, UTC)")

    # Time-of-day weighting
    parser.add_argument("--business_hours", default="08:00-18:00",
                        help="Business hours window (HH:MM-HH:MM, default 08:00-18:00)")
    parser.add_argument("--business_bias", type=int, default=70,
                        help="Percentage of timestamps within business hours (0-100, default 70)")

    # Verbose logging
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    return parser.parse_args()

# ----------------------------
# Validation & date handling
# ----------------------------
def validate_args(args):
    logging.debug("Validating CLI arguments...")
    for path in [args.to_list, args.from_list, args.relay_hosts]:
        if not os.path.isfile(path):
            logging.error(f"File not found: {path}")
            sys.exit(1)

    for path in [args.body_dir, args.html_dir, args.attach_dir]:
        if not os.path.isdir(path):
            logging.error(f"Directory not found: {path}")
            sys.exit(1)

    if args.html_pct is not None and not (0 <= args.html_pct <= 100):
        logging.error("--html_pct must be between 0 and 100")
        sys.exit(1)
    if args.attach_pct is not None and not (0 <= args.attach_pct <= 100):
        logging.error("--attach_pct must be between 0 and 100")
        sys.exit(1)
    if args.subject_len is not None and args.subject_len < 1:
        logging.error("--subject_len must be >= 1")
        sys.exit(1)
    if args.num_emails is not None and args.num_emails <= 0:
        logging.error("--num_emails must be > 0")
        sys.exit(1)
    if args.max_attachments is not None and args.max_attachments < 1:
        logging.error("--max_attachments must be >= 1")
        sys.exit(1)

    validate_date_range_args(args)

    if args.date_start and args.date_end:
        bh_start_min, bh_end_min = parse_business_hours(args.business_hours)
        if not (0 <= args.business_bias <= 100):
            logging.error("--business_bias must be between 0 and 100")
            sys.exit(1)
        if bh_start_min >= bh_end_min:
            logging.error("--business_hours must have start < end within same day (no overnight windows).")
            sys.exit(1)

    logging.debug("Validation passed.")

def parse_date_utc(date_str: str) -> datetime:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logging.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
        sys.exit(1)
    return dt.replace(tzinfo=timezone.utc)

def validate_date_range_args(args):
    if args.date_start or args.date_end:
        if not (args.date_start and args.date_end):
            logging.error("Both --date_start and --date_end must be provided together.")
            sys.exit(1)
        start = parse_date_utc(args.date_start)
        end = parse_date_utc(args.date_end) + timedelta(days=1) - timedelta(seconds=1)
        if start > end:
            logging.error("--date_start cannot be after --date_end")
            sys.exit(1)

def parse_business_hours(spec: str) -> Tuple[int, int]:
    m = re.match(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$", spec.strip())
    if not m:
        logging.error(f"Invalid --business_hours format: {spec}. Use HH:MM-HH:MM (e.g., 09:00-17:30).")
        sys.exit(1)
    sh, sm, eh, em = map(int, m.groups())
    if not (0 <= sh <= 23 and 0 <= sm <= 59):
        logging.error(f"Invalid start time in --business_hours: {spec}")
        sys.exit(1)
    if not ((0 <= eh <= 24) and (0 <= em <= 59 if eh < 24 else em == 0)):
        logging.error(f"Invalid end time in --business_hours: {spec}")
        sys.exit(1)
    start_min = sh * 60 + sm
    end_min = (eh * 60 + em) if eh < 24 else 24 * 60
    return start_min, end_min

# ----------------------------
# Config merging
# ----------------------------
def load_config(args) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if args.profile:
        config.update(PROFILE_DEFAULTS[args.profile])

    for key in ["html_pct", "attach_pct", "subject_len", "num_emails", "output_dir"]:
        val = getattr(args, key)
        if val is not None:
            config[key] = val

    config.update({
        "to_list": args.to_list,
        "from_list": args.from_list,
        "body_dir": args.body_dir,
        "html_dir": args.html_dir,
        "attach_dir": args.attach_dir,
        "relay_hosts": args.relay_hosts,
        "selection_mode": args.selection_mode,
        "max_attachments": args.max_attachments,
        "seed": args.seed,
        "verbose": args.verbose,
    })

    if args.date_start and args.date_end:
        date_start = parse_date_utc(args.date_start)
        date_end = parse_date_utc(args.date_end) + timedelta(days=1) - timedelta(seconds=1)
        config["date_start"] = date_start
        config["date_end"] = date_end
        bh_start_min, bh_end_min = parse_business_hours(args.business_hours)
        config["business_start_min"] = bh_start_min
        config["business_end_min"] = bh_end_min
        config["business_bias"] = int(args.business_bias)

    out_dir = Path(config["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    return config

# ----------------------------
# Helpers: file loading & selection
# ----------------------------
def read_list_file(path: str) -> List[str]:
    items: List[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if s:
                items.append(s)
    return items

def list_text_files(directory: str) -> List[Path]:
    exts = {".txt", ".md", ".text"}
    return [p for p in Path(directory).glob("*") if p.is_file() and p.suffix.lower() in exts]

def list_html_files(directory: str) -> List[Path]:
    exts = {".html", ".htm"}
    return [p for p in Path(directory).glob("*") if p.is_file() and p.suffix.lower() in exts]

def list_any_files(directory: str) -> List[Path]:
    return [p for p in Path(directory).glob("*") if p.is_file()]

def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def strip_html(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def sanitize_subject(s: str) -> str:
    return re.sub(r"[\r\n]+", " ", s).strip()

def weighted_choice(pairs: List[Tuple[int, float]], max_cap: int) -> int:
    items, weights = zip(*[(c, w) for c, w in pairs if c <= max_cap])
    total = sum(weights)
    if total <= 0:
        return 1
    r = random.random() * total
    upto = 0.0
    for item, w in zip(items, weights):
        if upto + w >= r:
            return item
        upto += w
    return items[-1]

class Selector:
    def __init__(self, mode: str = "random"):
        self.mode = mode
        self._idx: Dict[int, int] = {}

    def choose(self, key: int, items: List[Any]) -> Any:
        if not items:
            raise ValueError("Selection list is empty.")
        if self.mode == "random":
            choice = random.choice(items)
            logging.debug(f"Random selected (key {key}): {choice}")
            return choice
        i = self._idx.get(key, 0)
        value = items[i % len(items)]
        self._idx[key] = (i + 1) % len(items)
        logging.debug(f"Linear selected (key {key} idx {i}): {value}")
        return value

# ----------------------------
# Date utilities
# ----------------------------
def random_date_in_range(start: datetime, end: datetime) -> datetime:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Start/end must be timezone-aware")
    delta_seconds = (end - start).total_seconds()
    if delta_seconds < 0:
        raise ValueError("Start must be <= end")
    offset = random.uniform(0, delta_seconds)
    return start + timedelta(seconds=offset)

def random_date_weighted(
    start: datetime,
    end: datetime,
    business_start_min: int,
    business_end_min: int,
    business_bias: int,
) -> datetime:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Start/end must be timezone-aware")
    if start.date() > end.date():
        raise ValueError("Start date must be <= end date")

    day_span = (end.date() - start.date()).days
    day_offset = random.randint(0, day_span)
    day = start.date() + timedelta(days=day_offset)

    in_business = (random.randint(1, 100) <= business_bias)

    if in_business and business_start_min < business_end_min:
        minute_in_day = random.randint(business_start_min, business_end_min - 1)
    else:
        off1 = list(range(0, business_start_min))
        off2 = list(range(business_end_min, 24 * 60))
        off_all = off1 + off2
        if not off_all:
            minute_in_day = random.randint(business_start_min, business_end_min - 1)
        else:
            minute_in_day = random.choice(off_all)

    hour = minute_in_day // 60
    minute = minute_in_day % 60
    second = random.randint(0, 59)

    dt = datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=timezone.utc)
    if dt < start:
        dt = start
    elif dt > end:
        dt = end
    return dt

# ----------------------------
# Engine: headers & message
# ----------------------------
def parse_domain_from_email(addr: str) -> str:
    parts = addr.split("@", 1)
    return parts[1] if len(parts) == 2 else "localhost"

def gen_received_headers(
    relay_hosts: List[str],
    hops_min: int = 1,
    hops_max: int = 3,
    base_date: Optional[datetime] = None,
) -> List[str]:
    if not relay_hosts:
        return []
    hops = random.randint(hops_min, hops_max)
    chain = [random.choice(relay_hosts) for _ in range(hops + 1)]
    headers: List[str] = []

    anchor = base_date or datetime.now(timezone.utc)
    oldest = anchor - timedelta(minutes=random.randint(5, 15))
    hop_times = []
    t = oldest
    for _ in range(hops):
        t = t + timedelta(seconds=random.randint(30, 90))
        hop_times.append(t)

    for i in range(hops):
        src = chain[i]
        dst = chain[i + 1]
        pseudo_id = f"{random.randrange(16**8):08x}"
        date_str = formatdate(hop_times[i].timestamp(), localtime=False)
        h = f"from {src} by {dst} with ESMTP id {pseudo_id}; {date_str}"
        headers.append(h)

    return headers

def guess_mime_type(path: Path) -> Tuple[str, str]:
    ctype, encoding = mimetypes.guess_type(str(path))
    if ctype is None:
        return "application", "octet-stream"
    maintype, subtype = ctype.split("/", 1)
    return maintype, subtype

def build_email(
    from_addr: str,
    to_addr: str,
    is_html: bool,
    subject_len: int,
    text_body: str,
    html_body: Optional[str],
    attach_paths: List[Path],
    relay_hosts: List[str],
    msg_date: Optional[datetime] = None,
) -> EmailMessage:

    msg = EmailMessage()
    for rh in gen_received_headers(relay_hosts, base_date=msg_date):
        msg["Received"] = rh

    msg["From"] = from_addr
    msg["To"] = to_addr

    from_domain = parse_domain_from_email(from_addr)
    msg["Message-ID"] = make_msgid(domain=from_domain)

    if msg_date:
        msg["Date"] = formatdate(msg_date.timestamp(), localtime=False)
    else:
        msg["Date"] = formatdate(localtime=True)

    msg["X-Mailer"] = "email_builder/1.0"

    if is_html and html_body is not None:
        subj_source = strip_html(html_body)
    else:
        subj_source = text_body
    subject = sanitize_subject(subj_source[:subject_len]) or "No subject"
    msg["Subject"] = subject

    if is_html and html_body is not None:
        fallback_text = strip_html(html_body) if not text_body else text_body
        msg.set_content(fallback_text or "(no text)")
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(text_body or "(no text)")

    for ap in attach_paths:
        try:
            maintype, subtype = guess_mime_type(ap)
            data = ap.read_bytes()
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=ap.name)
        except Exception as e:
            logging.warning(f"Skipping attachment '{ap}': {e}")

    return msg

# ----------------------------
# Generation loop
# ----------------------------
def run_generation(config: Dict[str, Any]) -> None:
    if config.get("seed") is not None:
        random.seed(config["seed"])
        logging.info(f"Random seed set to {config['seed']}")

    to_addrs = read_list_file(config["to_list"])
    from_addrs = read_list_file(config["from_list"])
    relay_hosts = read_list_file(config["relay_hosts"])
    text_files = list_text_files(config["body_dir"])
    html_files = list_html_files(config["html_dir"])
    attach_files = list_any_files(config["attach_dir"])

    if not to_addrs:
        logging.error("Recipient list is empty.")
        sys.exit(1)
    if not from_addrs:
        logging.error("Sender list is empty.")
        sys.exit(1)
    if not text_files and not html_files:
        logging.error("Both body_dir (text) and html_dir are empty. Provide at least one.")
        sys.exit(1)
    if not text_files:
        logging.warning("No plain-text body files found; using stripped HTML for text fallback.")
    if not html_files and config["html_pct"] > 0:
        logging.warning("No HTML templates found; all emails will be plain text.")
    if not attach_files and config["attach_pct"] > 0:
        logging.warning("No attachment files found; attach_pct > 0 requested but none available.")

    selector = Selector(config["selection_mode"])
    total = int(config["num_emails"])
    html_probability = (config["html_pct"] / 100.0)
    attach_probability = (config["attach_pct"] / 100.0)
    out_dir = Path(config["output_dir"])
    max_attachments = int(config["max_attachments"])

    date_start: Optional[datetime] = config.get("date_start")
    date_end: Optional[datetime] = config.get("date_end")
    bh_start_min: Optional[int] = config.get("business_start_min")
    bh_end_min: Optional[int] = config.get("business_end_min")
    business_bias: Optional[int] = config.get("business_bias")

    logging.info(f"Generating {total} emails into '{out_dir.resolve()}'")
    logging.debug(f"HTML probability: {html_probability:.2f}, Attachment probability: {attach_probability:.2f}")
    logging.debug(f"Selection mode: {config['selection_mode']}")
    if date_start and date_end:
        logging.info(f"Randomizing dates between {date_start.isoformat()} and {date_end.isoformat()} (UTC)")
        logging.info(f"Time-of-day weighting: {business_bias}% within {mins_to_hhmm(bh_start_min)}-{mins_to_hhmm(bh_end_min)} UTC")

    KEY_FROM = 1
    KEY_TO = 2
    KEY_TEXT = 3
    KEY_HTML = 4
    KEY_ATTACH = 5

    for i in range(1, total + 1):
        from_addr = selector.choose(KEY_FROM, from_addrs)
        to_addr = selector.choose(KEY_TO, to_addrs)

        choose_html = (random.random() < html_probability) and bool(html_files)
        chosen_text = ""
        chosen_html = None

        if choose_html:
            html_path = selector.choose(KEY_HTML, html_files)
            try:
                chosen_html = load_text(html_path)
            except Exception as e:
                logging.warning(f"Failed to load HTML template '{html_path}': {e}")
                chosen_html = None
                choose_html = False

        if not choose_html:
            if text_files:
                text_path = selector.choose(KEY_TEXT, text_files)
                try:
                    chosen_text = load_text(text_path)
                except Exception as e:
                    logging.warning(f"Failed to load text body '{text_path}': {e}")
                    chosen_text = "(no text)"
            else:
                html_path = selector.choose(KEY_HTML, html_files)
                try:
                    chosen_html = load_text(html_path)
                    chosen_text = strip_html(chosen_html)
                except Exception as e:
                    logging.warning(f"Failed to load fallback HTML '{html_path}': {e}")
                    chosen_text = "(no text)"
                choose_html = False

        attach_list: List[Path] = []
        if attach_files and (random.random() < attach_probability):
            count = weighted_choice(ATTACH_COUNT_DIST, max_cap=max_attachments)
            if config["selection_mode"] == "linear":
                for _ in range(count):
                    attach_list.append(selector.choose(KEY_ATTACH, attach_files))
            else:
                if count <= len(attach_files):
                    attach_list = random.sample(attach_files, count)
                else:
                    attach_list = list(attach_files)
                    while len(attach_list) < count:
                        attach_list.append(random.choice(attach_files))

        msg_date: Optional[datetime] = None
        if date_start and date_end:
            if bh_start_min is not None and bh_end_min is not None and business_bias is not None:
                msg_date = random_date_weighted(
                    date_start, date_end, bh_start_min, bh_end_min, business_bias
                )
            else:
                msg_date = random_date_in_range(date_start, date_end)

        msg = build_email(
            from_addr=from_addr,
            to_addr=to_addr,
            is_html=choose_html,
            subject_len=int(config["subject_len"]),
            text_body=chosen_text,
            html_body=chosen_html,
            attach_paths=attach_list,
            relay_hosts=relay_hosts,
            msg_date=msg_date,
        )

        filename = f"email_{i:06d}.eml"
        out_path = out_dir / filename
        try:
            with open(out_path, "wb") as f:
                f.write(bytes(msg))
        except Exception as e:
            logging.error(f"Failed to write '{out_path}': {e}")
            sys.exit(1)

        if i % 100 == 0 or i == total:
            logging.info(f"Wrote {i}/{total} emails")

    logging.info("Generation complete.")

# ----------------------------
# Utilities
# ----------------------------
def mins_to_hhmm(mins: Optional[int]) -> str:
    if mins is None:
        return "--:--"
    h = mins // 60
    m = mins % 60
    return f"{h:02d}:{m:02d}"

# ----------------------------
# Entrypoint
# ----------------------------
def main():
    args = parse_args()
    setup_logging(args.verbose)
    logging.info("Starting Email Builder...")
    validate_args(args)
    config = load_config(args)
    logging.info("Configuration loaded.")
    logging.debug(f"Final configuration: {config}")
    run_generation(config)

if __name__ == "__main__":
    main()
