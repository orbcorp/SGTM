# Rotating the SGTM GitHub Token

When the GitHub PAT expires, SGTM stops working. The Lambda will still receive webhooks, but all GitHub GraphQL API calls fail with `401 Unauthorized` / `Bad credentials`. You'll notice because Asana stops getting updates for PRs.

## How to verify it's a token issue

Check CloudWatch logs for `/aws/lambda/sgtm`. Look for errors like:

```
ValueError: Error in graphql query:
{'data': None, 'errors': [{'message': 'HTTP Error 401: Unauthorized', ...}]}
```

If you see `Bad credentials` with a 401 status, the GitHub token is expired or revoked.

## Steps to rotate the token

### 1. Regenerate the GitHub PAT

1. Log in to GitHub as the SGTM bot user:
   - Sign in with the bot's Google account (credentials are in 1Password, search for "SGTM" or "sgtm bot")
   - GitHub will prompt for MFA. Open the authenticator app (also in 1Password) and enter the code from the SGTM GitHub token entry
2. Go to the token directly at https://github.com/settings/tokens/2171649983 (or find it under https://github.com/settings/tokens)
3. It should say that it is expired. Click **Regenerate**
4. Copy the new token

The PAT needs these scopes (regenerate should take care of this for you):
- `repo` (full control of private repositories)
- `read:org` (read org and team membership, read org projects)

### 2. Update the token in S3

1. Go to the S3 bucket: https://us-east-1.console.aws.amazon.com/s3/buckets/orb-terraform-api-sgtm?region=us-east-1
2. Download the `sgtm-keys` file
3. Rename the old file with a backup name like `sgtm-keys-backup-YYYY-MM-DD`
4. Edit the downloaded file and replace the `GITHUB_API_KEY` value with the new token
5. Upload the updated file as `sgtm-keys` (same original name)

### 3. Force the Lambda to pick up the new token

The token is read from S3 on Lambda cold start. To force a restart:

1. Go to the Lambda function `sgtm` in the AWS console
2. Go to **Configuration > Environment variables**
3. Edit and add or update a dummy variable (e.g., `RESTART=1` or increment its value)
4. Save

The next webhook invocation will use the new token.

### 4. Verify it's working

Trigger a webhook event (comment on a PR, open a PR, etc.) and check CloudWatch logs for `/aws/lambda/sgtm`. You should see successful GraphQL responses instead of 401 errors.
