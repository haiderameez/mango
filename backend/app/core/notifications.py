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
        return

    try:
        import boto3

        boto3.client("sns", region_name=settings.aws_region).publish(
            TopicArn=settings.aws_sns_topic_arn,
            Subject=subject[:100],
            Message=message,
        )
    except Exception:
        logger.exception("Failed to publish notification for incident %s", incident.id)
