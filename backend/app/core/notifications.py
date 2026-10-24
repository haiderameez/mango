import json
import logging

from app.core.config import settings
from app.models.incident import Incident

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "api_key"}


def notify_incident_created(incident: Incident) -> None:
    """Best-effort SNS publish. Never raises: a notification failure must not cost us an
    incident. With no topic configured the notification is logged instead."""
    subject = f"[Mango][{incident.severity.value}] Incident #{incident.id}"
    message = json.dumps(
        {
            "incident_id": incident.id,
            "title": incident.title,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "created_by": incident.created_by,
            "assigned_to": incident.assigned_to,
        }
    )

    if not settings.aws_sns_topic_arn:
        logger.info("SNS not configured, notification not sent: %s %s", subject, message)
    else:
        try:
            import boto3

            boto3.client("sns", region_name=settings.aws_region).publish(
                TopicArn=settings.aws_sns_topic_arn,
                Subject=subject[:100],
                Message=message,
            )
        except Exception:
            logger.exception("Failed to publish notification for incident %s", incident.id)

    _notify_slack(
        f"{subject}\n{incident.title}\nStatus: {incident.status.value}"
    )


def notify_investigation_completed(incident: Incident, report: str | None) -> None:
    probable_cause = ""
    if report:
        lines = report.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("## Likely root cause"):
                probable_cause = next(
                    (candidate.strip() for candidate in lines[index + 1:] if candidate.strip()),
                    "",
                )
                break
    _notify_slack(
        f"[Mango] Investigation complete for #{incident.id}: {incident.title}\n"
        f"Probable cause: {probable_cause or 'See incident report.'}"
    )


def notify_escalation(incident: Incident, target_user: str) -> None:
    _notify_slack(
        f"[Mango] Escalated {incident.severity.value} incident #{incident.id}: "
        f"{incident.title}\nAssigned to: {target_user}"
    )


def _notify_slack(text: str) -> None:
    if not settings.slack_webhook_url:
        return
    try:
        import httpx

        response = httpx.post(settings.slack_webhook_url, json={"text": text}, timeout=3.0)
        response.raise_for_status()
    except Exception as error:
        logger.warning("Failed to send Slack notification (%s)", type(error).__name__)
