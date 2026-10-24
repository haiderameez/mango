param(
    [Parameter(Mandatory = $true)] [string] $Region,
    [Parameter(Mandatory = $true)] [string] $ApiToken,
    [string] $StackName = 'mango-free-monthly'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw 'Install and configure AWS CLI v2 before deploying.'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3 is required to render the inline Lambda source.'
}
if ($ApiToken.Length -lt 32) { throw 'ApiToken must contain at least 32 characters.' }
if ($StackName -notmatch '^[a-z][a-z0-9-]{1,49}$') {
    throw 'StackName must use 1-50 lowercase letters, digits, or hyphens and start with a letter.'
}

$templatePath = Join-Path $PSScriptRoot 'free-monthly.yml'
$handlerPath = Join-Path $PSScriptRoot 'free_monthly_handler.py'
$renderedPath = Join-Path ([IO.Path]::GetTempPath()) ("mango-free-monthly-{0}.yml" -f [guid]::NewGuid())
try {
    & python (Join-Path $PSScriptRoot 'render-free-monthly.py') `
        --template $templatePath --handler $handlerPath --output $renderedPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not render the Lambda handler into the CloudFormation template.' }
    & aws sts get-caller-identity --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'AWS credentials are not configured or cannot access STS.' }
    & aws cloudformation deploy `
        --template-file $renderedPath `
        --stack-name $StackName `
        --region $Region `
        --parameter-overrides "ApiToken=$ApiToken"
    if ($LASTEXITCODE -ne 0) { throw 'Free-allowance Mango stack deployment failed.' }
    & aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query 'Stacks[0].Outputs' `
        --output table
    if ($LASTEXITCODE -ne 0) { throw 'Deployment completed, but output lookup failed.' }
}
finally {
    Remove-Item -LiteralPath $renderedPath -Force -ErrorAction SilentlyContinue
}
