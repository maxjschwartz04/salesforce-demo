"""
Suggests which of the team's own real outreach scripts fits an account's
current staleness situation -- never invents new copy. Every template
below is lifted from a real script the team already uses (see the
`source` on each), with blanks filled from real account/contact data.
Anything the SOURCE script itself leaves as a bracket placeholder
([topic], [WEBINAR TITLE], etc.) stays a bracket here too -- that's
customization the source material already expects a human to do by hand,
not something this tool should guess at.

Scope, deliberate:
- Only "never_engaged", "cooling_off", and "stalled" get a suggestion --
  "new" and "on_pace" don't need one (see staleness.py).
- Staleness-triggered only. Event-triggered situations from the same
  script library ("they just attended a webinar," "they just got
  promoted") are a different kind of check -- they fire off a recent
  EVENT, not an overall status -- and aren't built yet.
- Which real template gets picked, within a status, depends on whether
  the account has subscribed to FDA Today or attended a webinar (see
  campaign_parser.has_subscribed_to_newsletter /
  has_attended_webinar) -- leading with the newsletter ask (lowest
  commitment) before a webinar invite, matching the order the real intro
  scripts themselves use. Free-trial status isn't tracked yet: that data
  lives on Product Baskets, a different Salesforce object than anything
  in the exports this pipeline currently parses (see
  BDS_Best_Practices.pdf).

Usage:
    from email_templates import suggest_email_template
    suggest_email_template(row)  # row is a tracker.py row dict
"""

# Real script, lightly trimmed to the parts we can fill from real data --
# see AgencyIQ_Email_Templates_2.pdf, "4. Newsletter Invite – LS."
NEWSLETTER_INVITE_TEMPLATE = {
    "id": "newsletter_invite",
    "source": "AgencyIQ_Email_Templates_2.pdf — Newsletter Invite (LS)",
    "subject": "AgencyIQ | Regulatory insights",
    "body": (
        "Hi {first_name},\n\n"
        "I'm reaching out from AgencyIQ with a resource I thought might be helpful in your role at {account}. "
        "Our free regulatory newsletter, FDA Today, provides a quick roundup of key developments from the FDA.\n\n"
        "Hope it saves time and helps with planning ahead.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Real script -- see MASTER_KEY_BD_Scripts.pdf, "Webinar Invite" (Chemicals
# section, generalizes across verticals). BDS_Best_Practices.pdf says
# invites should go out roughly a week ahead of the date.
WEBINAR_INVITE_TEMPLATE = {
    "id": "webinar_invite",
    "source": "MASTER_KEY_BD_Scripts.pdf — Webinar Invite",
    "subject": "AgencyIQ Webinar Invite",
    "body": (
        "Hi {first_name},\n\n"
        "I wanted to personally invite you to AgencyIQ's upcoming webinar on [DATE & TIME], titled [WEBINAR "
        "TITLE]. Our research team will review recent developments relevant to {account} and take live "
        "questions.\n\n"
        "You can sign up here: [LINK]\n\n"
        "All the best,\n[Your Name]"
    ),
}

# Real script -- see AIQ_Outreach_Templates_1.pdf, Follow-up Script #2
# ("Sample Content"). For an account that already has the newsletter and
# has attended a webinar -- an ordinary continuing touch, not an
# escalation.
FOLLOWUP_SAMPLE_CONTENT_TEMPLATE = {
    "id": "followup_sample_content",
    "source": "AIQ_Outreach_Templates_1.pdf — Follow-up Script #2 (Sample Content)",
    "subject": "Is shifting FDA policy on [topic] impacting your regulatory strategy?",
    "body": (
        "{first_name} —\n\n"
        "I was wondering if shifting FDA guidance and policy on [topic] has been driving frequent changes in "
        "regulatory strategy at {account}.\n\n"
        "If so, I'm writing to see if you have 30 minutes to connect this [day of week] at [time] to hear how "
        "AgencyIQ research and monitoring on [topic] can support your team.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track Re-Approach
# Script #1 ("Updated Pricing and Terms"). This section exists for exactly
# this situation: an established relationship that's gone quiet.
SLOW_TRACK_REAPPROACH_TEMPLATE = {
    "id": "slow_track_reapproach",
    "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #1",
    "subject": "AgencyIQ Updates – time to connect?",
    "body": (
        "{first_name},\n\n"
        "It's been a while — how are you?\n\n"
        "I thought it timely for us to reconnect on the AgencyIQ platform at {account}. We've seen several new "
        "platform releases and enhanced FDA coverage since we last spoke, and I wanted to share those updates "
        "with you.\n\n"
        "If you still think our resources would be valuable, I think it'd be worthwhile to have a quick "
        "discussion. Let me know what you think.\n\n"
        "Best,\n[Your Name]"
    ),
}


def _fill(template, first_name, account):
    return {
        "id": template["id"],
        "source": template["source"],
        "subject": template["subject"],
        "body": template["body"].format(first_name=first_name, account=account),
    }


def suggest_email_template(row):
    """row: a tracker.py row dict -- needs 'actionable_status', 'account',
    'contacts' (from campaign_parser.top_contacts), and 'attended_webinar'
    / 'subscribed_to_newsletter' (from campaign_parser.has_attended_webinar
    / has_subscribed_to_newsletter, precomputed once in run_tracker).

    Returns None for "new"/"on_pace"/anything else -- there's nothing to
    suggest sending. Otherwise returns {id, source, subject, body} with
    the real template's fillable blanks completed from real data; blanks
    the SOURCE script itself leaves open ([topic], [DATE & TIME], etc.)
    are left as-is for a rep to complete, same as the source material
    expects."""
    status = row.get("actionable_status")
    if status not in ("never_engaged", "cooling_off", "stalled"):
        return None

    contacts = row.get("contacts") or []
    first_name = contacts[0].get("first_name") or "there" if contacts else "there"
    account = row.get("account") or "your organization"

    if status == "stalled":
        template = SLOW_TRACK_REAPPROACH_TEMPLATE
    elif not row.get("subscribed_to_newsletter"):
        template = NEWSLETTER_INVITE_TEMPLATE
    elif not row.get("attended_webinar"):
        template = WEBINAR_INVITE_TEMPLATE
    else:
        template = FOLLOWUP_SAMPLE_CONTENT_TEMPLATE

    return _fill(template, first_name, account)
