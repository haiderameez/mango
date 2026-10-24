param(
    [Parameter(Mandatory = $true)] [string] $Region,
    [Parameter(Mandatory = $true)] [string] $CertificateArn,
    [Parameter(Mandatory = $true)] [string] $DomainName,
    [Parameter(Mandatory = $true)] [string] $LLMApiKeySecretArn,
    [ValidateSet('gemini', 'openrouter', 'anthropic')] [string] $LLMProvider = 'openrouter',
    [string] $StackName = 'mango',
    [string] $NotificationEmail = '',
    [switch] $AllowPaidResources
)

$ErrorActionPreference = 'Stop'

if (-not $AllowPaidResources) {
    throw 'This ECS/RDS/ElastiCache stack is not covered by recurring free allowances. Use deploy-free-monthly.ps1, or pass -AllowPaidResources only when you intend to deploy billable services.'
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw 'Install and configure the AWS CLI v2 before running this deployment script.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker before building the Mango backend image.'
}
if ($StackName -notmatch '^[a-z][a-z0-9-]{1,19}$') {
    throw 'StackName must be 2-20 lowercase letters, digits, or hyphens and start with a letter.'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$ecrTemplate = Join-Path $PSScriptRoot 'ecr.yml'
$stackTemplate = Join-Path $PSScriptRoot 'mango.yml'
$ecrStack = "$StackName-images"
$repositoryName = "$StackName-backend"

& aws sts get-caller-identity --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'AWS credentials are not configured or cannot access STS.' }

& aws cloudformation deploy `
    --template-file $ecrTemplate `
    --stack-name $ecrStack `
    --region $Region `
    --parameter-overrides "RepositoryName=$repositoryName"
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Mango ECR repository.' }

$repositoryUri = (& aws cloudformation describe-stacks `
    --stack-name $ecrStack `
    --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='RepositoryUri'].OutputValue" `
    --output text).Trim()
if ($LASTEXITCODE -ne 0 -or -not $repositoryUri) { throw 'Could not read the Mango ECR repository URI.' }

$imageTag = 'release-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$imageUri = "$repositoryUri`:$imageTag"
$registry = $repositoryUri.Split('/')[0]
& aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { throw 'Could not authenticate Docker to ECR.' }

Push-Location $repoRoot
try {
    & docker build --tag $imageUri --file backend/Dockerfile backend
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the Mango backend image.' }
    & docker push $imageUri
    if ($LASTEXITCODE -ne 0) { throw 'Could not push the Mango backend image to ECR.' }
}
finally {
    Pop-Location
}

$parameters = @(
    "EnvironmentName=$StackName",
    "BackendImage=$imageUri",
    "CertificateArn=$CertificateArn",
    "DomainName=$DomainName",
    "LLMProvider=$LLMProvider",
    "LLMApiKeySecretArn=$LLMApiKeySecretArn"
)
if ($NotificationEmail) { $parameters += "NotificationEmail=$NotificationEmail" }

& aws cloudformation deploy `
    --template-file $stackTemplate `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameter-overrides $parameters
if ($LASTEXITCODE -ne 0) { throw 'Mango infrastructure deployment failed. Inspect CloudFormation stack events.' }

& aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --query 'Stacks[0].Outputs' `
    --output table
if ($LASTEXITCODE -ne 0) { throw 'Deployment completed, but output lookup failed.' }
