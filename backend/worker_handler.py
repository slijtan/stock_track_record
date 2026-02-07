"""
AWS Lambda handler for the Stock Track Record Worker.

This module processes SQS messages to handle channel processing jobs.
"""
import json
from app.services.processing_service import process_channel


def handler(event, context):
    """
    Process SQS messages containing channel processing jobs.

    Each message should contain:
    {
        "channel_id": "uuid-here"
    }
    """
    print(f"Received {len(event.get('Records', []))} messages")

    for record in event.get('Records', []):
        try:
            body = json.loads(record['body'])
            channel_id = body.get('channel_id')

            if not channel_id:
                print(f"Missing channel_id in message: {body}")
                continue

            print(f"Processing channel: {channel_id}")

            try:
                process_channel(channel_id)
                print(f"Successfully processed channel: {channel_id}")
            except Exception as e:
                print(f"Error processing channel {channel_id}: {e}")
                raise  # Re-raise to mark message as failed

        except json.JSONDecodeError as e:
            print(f"Invalid JSON in message: {e}")
            continue

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Processing complete'})
    }
