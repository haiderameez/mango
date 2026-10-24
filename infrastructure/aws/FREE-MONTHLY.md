# Mango AWS free monthly allowance profile

This profile is a separate, intentionally small incident API. It uses a Lambda function and
one provisioned DynamoDB table, both of which have recurring Free Tier allowances. It does
not deploy ECS/Fargate, RDS, ElastiCache, an Application Load Balancer, API Gateway, NAT,
Secrets Manager, Route 53, or a static-website bucket.

The current Mango application depends on FastAPI, PostgreSQL with pgvector, Redis/Celery, and
multiple workers. This profile does not run those components or provide the full console,
log detection, historical retrieval, or AI investigation pipeline. It implements only a
small authenticated incident API: create, list, retrieve, and advance an incident through
`OPEN` → `INVESTIGATING` → `RESOLVED`.

## AWS resources and allowance use

| Resource | Configuration | Free allowance relevant to this profile |
|---|---|---|
| Lambda | 128 MB, 3-second timeout, reserved concurrency 1 | 1 million requests and 400,000 GB-seconds per month |
| DynamoDB | One provisioned table, 20 RCU / 6 WCU, single region | 25 RCU, 25 WCU, and 25 GB per month |
| Lambda Function URL | HTTPS endpoint; token checked in the handler | No separate endpoint charge; Lambda invocation pricing applies |
| IAM / CloudFormation | Narrow table policy and stack resources | No service charge for these resources |

The table caps incident creation at 10,000 rows; each description is limited to 1,000
characters. This keeps this profile's stored data far below the 25 GB DynamoDB allowance.
The DynamoDB free allowance is shared across the payer account and region, and Lambda's
allowance is shared across the account. Check the account's current Free Tier usage first:
other resources can consume some or all of the same allowances. AWS may charge a paid-plan
account when an allowance is exceeded. A public Function URL can still receive requests
that consume Lambda usage before the handler rejects a missing or invalid bearer token, so
this profile cannot promise a hard $0 bill under arbitrary traffic.

AWS's [Lambda pricing page](https://aws.amazon.com/lambda/pricing/), [DynamoDB pricing
page](https://aws.amazon.com/dynamodb/pricing/), and [Free Tier guide](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html)
describe the current limits. Recheck them before deploying.

## Deploy

Run from the repository root in PowerShell, after verifying the AWS Free Tier page shows
enough unused DynamoDB and Lambda allowance in the selected region/account:

```powershell
$token = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
./infrastructure/aws/deploy-free-monthly.ps1 -Region eu-north-1 -ApiToken $token
```

The script renders the Lambda source into the CloudFormation template and deploys it
directly. It does not create an ECR repository or artifact bucket. Keep the token in a
password manager; do not commit it or paste it into chat. The stack output includes the
Function URL. Send `Authorization: Bearer <token>` with requests, for example:

```powershell
Invoke-RestMethod -Method Post -Uri "$url/incidents" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType 'application/json' `
  -Body '{"title":"Checkout errors","severity":"HIGH"}'
Invoke-RestMethod -Uri "$url/incidents" -Headers @{ Authorization = "Bearer $token" }
```

The AWS Free Tier is an allowance, not an account-wide bill stop. Check service usage and
cost after deployment, and delete the stack when you no longer need the API:

```powershell
aws cloudformation delete-stack --stack-name mango-free-monthly --region eu-north-1
```

## Local verification

From `backend/`, run `./.venv/Scripts/python.exe -m pytest -q tests/test_free_monthly_handler.py`.
The tests use a small in-memory DynamoDB fake and do not contact AWS.
