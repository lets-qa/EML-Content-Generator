## Run Example
email_builder \
  --profile mixed_business \
  --to_list examples/to_list.txt \
  --from_list examples/from_list.txt \
  --body_dir examples/body_samples \
  --html_dir examples/html_samples \
  --attach_dir examples/attach_samples \
  --relay_hosts examples/relay_hosts.txt \
  --num_emails 5 \
  -v

## Options

| Argument           | Type      | Required | Possible Inputs / Example Values                | Description                                                      |
|--------------------|-----------|----------|------------------------------------------------|------------------------------------------------------------------|
| --profile          | str       | No       | mixed_business, internal_ops, marketing         | Predefined profile for defaults                                  |
| --to_list          | str (path)| Yes      | examples/to_list.txt                            | Path to recipient email list file                                |
| --from_list        | str (path)| Yes      | examples/from_list.txt                          | Path to sender email list file                                   |
| --body_dir         | str (path)| Yes      | examples/body_samples                           | Directory with plain text bodies                                 |
| --html_dir         | str (path)| Yes      | examples/html_samples                           | Directory with HTML bodies                                       |
| --attach_dir       | str (path)| Yes      | examples/attach_samples                         | Directory with attachments                                       |
| --relay_hosts      | str (path)| Yes      | examples/relay_hosts.txt                        | Path to relay hostnames file                                     |
| --html_pct         | int       | No       | 0-100, e.g. 88                                  | % of emails as HTML                                              |
| --attach_pct       | int       | No       | 0-100, e.g. 25                                  | % of emails with attachments                                     |
| --subject_len      | int       | No       | >=1, e.g. 50                                    | Number of chars for subject                                      |
| --num_emails       | int       | No       | >0, e.g. 1000                                   | Number of emails to generate                                     |
| --output_dir       | str (path)| No       | output_emails/                                  | Directory for output .eml files                                  |
| --selection_mode   | str       | No       | random, linear                                  | How items are selected (default: random)                         |
| --max_attachments  | int       | No       | >=1, e.g. 4                                     | Max attachments per email (default: 4)                           |
| --seed             | int       | No       | Any integer, e.g. 42                            | Random seed for reproducibility                                  |
| --date_start       | str       | No       | YYYY-MM-DD, e.g. 2025-09-01                     | Start date for timestamps                                        |
| --date_end         | str       | No       | YYYY-MM-DD, e.g. 2025-09-30                     | End date for timestamps                                          |
| --business_hours   | str       | No       | HH:MM-HH:MM, e.g. 08:00-18:00                   | Business hours window                                            |
| --business_bias    | int       | No       | 0-100, e.g. 70                                  | % timestamps within business hours                               |
| -v / --verbose     | flag      | No       | (no value, just include the flag)               | Enable verbose logging                                           |