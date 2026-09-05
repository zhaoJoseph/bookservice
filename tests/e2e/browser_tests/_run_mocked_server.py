"""
Runs the real app in this process with AWS faked via moto, for live_server
to launch as a subprocess.

moto's usual `mock_aws()` trick only works within the process that entered
it - it patches boto3 by extending BUILTIN_HANDLERS at import time, which a
separate test process's mock can't reach across into this one. So instead,
this script itself enters the mock (importing `moto` before `src.main`, so
the app's ses_client singleton gets auto-instrumented when it's constructed)
and stays inside it for the server's whole lifetime, then adds a debug-only
route so a separate test process can read back what got "sent" over real
HTTP instead of needing in-process access to moto's state.
"""
import sys
from pathlib import Path

# Running this as a plain script only puts this file's own directory on
# sys.path, not the repo root - unlike `python -m uvicorn ...`, which adds
# the cwd. `src` needs to be importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import botocore.exceptions
from moto import mock_aws

_mock = mock_aws()
_mock.start()

from src.main import app  # noqa: E402  (must import after mock_aws starts)
from src.aws.client import ses_client  # noqa: E402
from src.aws.config import aws_settings  # noqa: E402
from moto.core.models import DEFAULT_ACCOUNT_ID  # noqa: E402
from moto.ses.models import ses_backends  # noqa: E402

ses_client.v2_client.create_email_identity(EmailIdentity=aws_settings.SES_SOURCE_EMAIL)


@app.get("/__test__/sent_emails")
def _sent_emails():
    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    return [
        {
            "source": message.source,
            "subject": message.subject,
            "body": message.body,
            "destinations": message.destinations,
        }
        for message in backend.sent_messages
    ]


_real_send_email = ses_client.v2_client.send_email


def _raise_endpoint_unreachable(*args, **kwargs):
    raise botocore.exceptions.EndpointConnectionError(
        endpoint_url="https://email.us-east-1.amazonaws.com/"
    )


@app.post("/__test__/simulate_aws_down")
def _simulate_aws_down(down: bool = True):
    # Lets a test simulate an AWS outage without needing to reach into this
    # subprocess's memory (moto's mock_aws() state, like everything else
    # here, only exists in this process). Real toggle, not a fresh mock:
    # flips the same bound method the app actually calls.
    ses_client.v2_client.send_email = _raise_endpoint_unreachable if down else _real_send_email # type: ignore[assignment]
    return {"aws_down": down}


if __name__ == "__main__":
    import uvicorn

    host, port = sys.argv[1], int(sys.argv[2])
    uvicorn.run(app, host=host, port=port)
