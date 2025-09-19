
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
