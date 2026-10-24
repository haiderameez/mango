# Deploy Mango to AWS

This original ECS/RDS/ElastiCache deployment uses services that are not covered by recurring
monthly free allowances. If the requirement is to stay within monthly Free Tier allowances,
use [FREE-MONTHLY.md](FREE-MONTHLY.md) instead; it deploys a limited Lambda/DynamoDB incident
API. The free profile is not the full Mango application.

This CloudFormation stack runs Mango on ECS Fargate with an HTTPS Application Load Balancer,
private RDS PostgreSQL (including the `pgvector` extension installed by Alembic), private
ElastiCache Redis with TLS, CloudWatch logs and alarms, a generated JWT secret, and an SNS
incident topic. The API, investigation worker, ingestion worker, and Celery scheduler run as separate
services. Database and provider secrets are injected by ECS from Secrets Manager; the
application builds its connection strings inside each container.

The stack starts with one API task, one task for each worker, and one scheduler. It uses a
single-AZ PostgreSQL instance and one Redis cache node by default to limit the starting size.
ECS tasks receive public IPs for outbound provider access, but their security group accepts
inbound traffic only from the load balancer. PostgreSQL and Redis have no public route and
accept traffic only from Mango tasks. Increase the database/cache sizes and add redundancy
before using this as a production service.

## Prerequisites

- An AWS account with permissions for CloudFormation, ECR, ECS, EC2/VPC, RDS, ElastiCache,
  IAM, Secrets Manager, CloudWatch, Elastic Load Balancing, and SNS.
- AWS CLI v2, Docker, and an AWS credential profile configured locally.
- A domain name and an ACM certificate for that name in the deployment region. The domain
  must resolve to the load balancer after deployment.
- A provider API key stored as a **plain string** in AWS Secrets Manager. Create the secret
  in the same AWS region and pass its ARN; the deploy script never handles or prints the key.

For example, create the LLM secret in the AWS console under Secrets Manager. Choose “Other
type of secret”, enter the provider key as the secret value, and copy the resulting ARN. Do
not put credentials in this repository or in shell history.

## Deploy

From the repository root in PowerShell:

```powershell
./infrastructure/aws/deploy.ps1 `
  -Region us-east-1 `
  -CertificateArn arn:aws:acm:us-east-1:123456789012:certificate/replace-me `
  -DomainName mango.example.com `
  -LLMApiKeySecretArn arn:aws:secretsmanager:us-east-1:123456789012:secret:mango/llm-key-AbCdEf `
  -LLMProvider openrouter
```

The script verifies AWS access, creates an immutable ECR repository, builds and pushes the
backend image, deploys the stack, and prints its outputs. Add `-NotificationEmail
you@example.com` to subscribe that address to incident notifications and CloudWatch alarms;
AWS sends confirmation messages that the recipient must accept. Without it, copy
`IncidentTopicArn` and `OperationsTopicArn` from the stack outputs to connect other SNS
subscribers.

The `ConsoleUrl` output is the HTTPS console address. Create an ALIAS or CNAME record for
`DomainName` pointing to `LoadBalancerDnsName`. Then open `/health` and `/console` on that
domain. The first API task runs `alembic upgrade head` before serving traffic. Register a
user, then use the console or the normal auth endpoint. `DatabaseSecretArn` is available in
stack outputs for database administration; never place its value in task definitions.

## Verify live AWS behavior

After the services report steady state:

1. Check the API health endpoint and sign in to the console.
2. Create an incident and confirm an SNS message arrives at a confirmed subscription (or
   inspect the configured SNS subscriber).
3. Submit a small batch through `POST /ingest/logs`, then confirm the incident appears and
   its investigation completes. The ECS worker and scheduler logs are in the stack's
   `/ecs/<environment>/backend` CloudWatch log group.
4. Check the `Mango` ECS cluster, service metrics, and the API CPU / ALB 5xx CloudWatch
   alarms.

The stack cannot run these live checks until it is deployed in an AWS account. The default
database, cache, load balancer, and always-on Fargate services incur ongoing AWS charges;
check current regional pricing before deployment. The database has deletion protection and
retains a snapshot when the stack is removed. Turn off deletion protection deliberately
before a teardown, and preserve any data you need.
