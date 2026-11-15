"""Send the daily email that main.py --defer-email built.

The daily workflow runs this after "Commit output files", so the email only
goes out once the day is published on main. A gate or commit failure leaves
the email unsent; a later catch-up slot rebuilds and publishes the day and
sends it then. Nothing is ever emailed for an unpublished day.

Dedupe: before sending, curator.email_sender.send_campaign() asks Brevo for a
campaign already sent to the list on today's Eastern date and refuses if one
exists, or if Brevo cannot answer. The `force` flag in the pending file (set
by the force_email manual input) skips that check.

Exit codes:
  0  sent, or nothing to send (no pending file: --no-email or a skipped send),
     or Brevo already shows today's email (the duplicate was refused)
  1  the send was attempted or refused for any other reason (no key, Brevo
     error, Brevo check failed); the site is already committed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator import email_sender as es  # noqa: E402


def main(path: Path = es.PENDING_EMAIL_PATH) -> int:
    if not path.exists():
        print("No pending email (sent inline, --no-email, or skipped). Nothing to send.")
        return 0
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"::error::Pending email file is unreadable: {e}")
        return 1

    edition = es.edition_date().isoformat()
    if pending.get("edition") != edition:
        print(f"::error::Pending email is for {pending.get('edition')}, today is "
              f"{edition}. Not sending a stale edition.")
        return 1

    force = bool(pending.get("force"))
    if not force:
        try:
            already = es.brevo_sent_campaign()
        except es.BrevoCheckError as e:
            print(f"::error::Email not sent: {e}. The site is published. Check Brevo "
                  "by hand, then rerun with force_email if nothing went out.")
            return 1
        if already:
            print(f"::notice::Email already sent today (Brevo campaign {already.get('id')}). "
                  "Not sending again.")
            path.unlink()
            return 0

    # The check above already ran, so send_campaign skips its own.
    sent = es.send_campaign(pending["subject"], pending["html"], force=True)
    if sent:
        path.unlink()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
