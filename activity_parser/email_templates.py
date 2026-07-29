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
- Food sector only. The real script library has parallel Life Sciences /
  Food / Chemicals versions of most scripts (different newsletter names,
  different wording -- "FDA Today" vs "FDA Today: Food" vs "The
  Periodic"), and there's no reliable per-account vertical field in the
  Salesforce exports this pipeline parses to auto-route between them
  (checked: the Opportunity export has no industry/vertical column, and
  campaign-name vertical tags only cover a minority of engagement
  records). Rather than guess, this tool is scoped to the Food sector --
  the team's current growth focus anyway -- and every template below uses
  the real Food-flavored script. Feeding it non-food accounts is a
  by-hand decision left to whoever runs it (which .mhtml exports get
  passed in), not something this code filters for.
- Only "never_engaged", "cooling_off", and "stalled" get a suggestion --
  "new" and "on_pace" don't need one (see staleness.py).
- Staleness-triggered only. Event-triggered situations from the same
  script library ("they just attended a webinar," "they just got
  promoted") are a different kind of check -- they fire off a recent
  EVENT, not an overall status -- and don't fit this tool's trigger model
  anyway: by the time an account is flagged here, enough time has passed
  (14-21+ days, see staleness.py) that "thanks for attending yesterday's
  webinar" would already read as stale itself.
- Which real template gets picked, within a status, depends on whether
  the account has subscribed to FDA Today: Food or attended a webinar
  (see campaign_parser.has_subscribed_to_newsletter / has_attended_webinar)
  -- leading with the newsletter ask (lowest commitment) before a webinar
  invite, matching the order the real intro scripts themselves use. A
  cooling_off account that's already subscribed AND attended gets an
  ordinary content follow-up; a STALLED account in that same spot gets a
  free-trial offer instead -- the real scripts only extend a trial once a
  relationship is nearly lost ("Thanks for subscribing to FDA and EMA
  Today," the Food "thank you for subscribing" follow-up, and the breakup
  email all use it as a late-stage lever, not an early one). Within
  "stalled," the choice between the trial offer and the two Slow Track
  Re-Approach scripts depends first on that proven-engagement signal, then
  on whether the closed-won revival library (revival_library.py /
  suggestions.py) has a real precedent for this account's silence -- see
  suggest_email_template. Current trial-usage status still isn't tracked
  (that data lives on Product Baskets, a different Salesforce object than
  anything in the exports this pipeline currently parses -- see
  BDS_Best_Practices.pdf), so this can offer a trial to someone already on
  one; a real, known limitation, same shape as the other gaps above.

Usage:
    from email_templates import suggest_email_template
    suggest_email_template(row)  # row is a tracker.py row dict
"""

# Real script -- see AgencyIQ_Email_Templates_2.pdf, "3. Food Newsletter
# Invite," lightly trimmed to the parts we can fill from real data (the
# source script also pastes in a real recent edition, which this tool
# can't fabricate).
NEWSLETTER_INVITE_TEMPLATE = {
    "id": "newsletter_invite",
    "source": "AgencyIQ_Email_Templates_2.pdf — Food Newsletter Invite",
    "subject": "FDA Today: Food – Clear, Expert Insights for Food Regulatory Professionals",
    "body": (
        "Hi {first_name},\n\n"
        "Based on your role at {account}, I thought it might be useful to share a resource many food regulatory "
        "professionals use to stay current.\n\n"
        "AgencyIQ publishes a newsletter by regulatory specialists focused on food policy and oversight. It "
        "covers FDA and USDA developments, state-level actions, and emerging compliance considerations, all "
        "designed to help teams anticipate changes and prioritize what matters most.\n\n"
        "You can opt in to receive future issues if it aligns with your work by subscribing here.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Real script -- see MASTER_KEY_BD_Scripts.pdf, "Webinar Invite" (Chemicals
# section). The real library uses this identical structure across
# verticals with just the industry noun swapped (the same pattern the real
# Newsletter Invite and "Congratulations on your new role" scripts use for
# their own LS/Food variants), so this substitutes "food" for "chemicals"
# rather than inventing new wording. BDS_Best_Practices.pdf says invites
# should go out roughly a week ahead of the date.
WEBINAR_INVITE_TEMPLATE = {
    "id": "webinar_invite",
    "source": "MASTER_KEY_BD_Scripts.pdf — Webinar Invite (Food adaptation)",
    "subject": "AgencyIQ Webinar Invite",
    "body": (
        "Hi {first_name},\n\n"
        "Staying ahead of the curve on food regulatory policy has become much less predictable. That's why I "
        "wanted to personally invite you to AgencyIQ's upcoming webinar at [DATE & TIME], titled [WEBINAR "
        "TITLE].\n\n"
        "Our food regulatory team will review recent developments relevant to {account} and take your questions "
        "live.\n\n"
        "You can sign up here: [LINK]\n\n"
        "All the best,\n[Your Name]"
    ),
}

# Real script -- see AIQ_Outreach_Templates_1.pdf's "Sample Content"
# follow-up, adapted with the food-specific content-share pattern from the
# real "FDA Revokes 52 Food Standards" example (Food scripts, MASTER_KEY
# BD Scripts) rather than the source's "[topic/therapeutic area]" LS
# framing. For an account that already has the newsletter and has
# attended a webinar but hasn't reached the trial-ready bar yet.
FOLLOWUP_SAMPLE_CONTENT_TEMPLATE = {
    "id": "followup_sample_content",
    "source": "AIQ_Outreach_Templates_1.pdf — Follow-up Script #2 (Sample Content, Food adaptation)",
    "subject": "Is a recent FDA or USDA food policy change impacting your regulatory strategy?",
    "body": (
        "{first_name} —\n\n"
        "I was wondering if a recent food regulatory development has been driving changes in strategy at "
        "{account}.\n\n"
        "If so, I'm writing to see if you have 30 minutes to connect this [day of week] at [time] to hear how "
        "AgencyIQ's food regulatory research and monitoring can support your team.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Real script -- see MASTER_KEY_BD_Scripts.pdf, "Thanks for subscribing to
# EMA and FDA Today," adapted to the Food newsletter and trimmed to the
# parts we can fill from real data (the source also pastes in specific
# real analyses this tool can't fabricate). The real library only extends
# a trial offer once someone's shown real engagement (subscribed AND
# attended a webinar here) -- never as a first move -- matching this
# script's own framing and the Food "thank you for subscribing" follow-up
# ("if you like our newsletter after reading a few, we'd be happy to show
# you...guest access").
TRIAL_OFFER_TEMPLATE = {
    "id": "trial_offer",
    "source": "MASTER_KEY_BD_Scripts.pdf — Thanks for Subscribing (Food adaptation, trial offer)",
    "subject": "More from AgencyIQ, beyond FDA Today: Food",
    "body": (
        "Hi {first_name},\n\n"
        "Thanks for subscribing to FDA Today: Food and for attending one of our webinars. These are a great way "
        "to stay informed, but they represent just a fraction of the food regulatory intelligence our team "
        "produces each week for companies like {account}.\n\n"
        "If it would help, I'd be happy to set you up with a complimentary trial login to explore our full "
        "platform coverage -- FDA, USDA, EPA, and state-level food developments in one place.\n\n"
        "Are there any current projects you're focused on where we could share deeper analysis?\n\n"
        "Best,\n[Your Name]"
    ),
}

# Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track Re-Approach
# Script #1 ("Updated Pricing and Terms"). This section exists for exactly
# this situation: an established relationship that's gone quiet. Leads
# with "we've seen real momentum" -- use it when the revival library
# (revival_library.py / suggestions.py) actually has a closed-won account
# that came back from a similar silence, i.e. there's real precedent to
# imply that with.
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

# Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track Re-Approach
# Script #3 ("Requesting Assistance in Future of Product"). Doesn't lean
# on "we've seen this pattern before" the way Script #1 does -- asks for
# product feedback instead. Used when the revival library has no
# comparable closed-won precedent for this account's silence, so there's
# nothing real to back up a "we've revived accounts like yours" framing.
SLOW_TRACK_PRODUCT_FEEDBACK_TEMPLATE = {
    "id": "slow_track_product_feedback",
    "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #3",
    "subject": "AgencyIQ Product Roadmap – your assistance?",
    "body": (
        "{first_name},\n\n"
        "I hope you've all been well since we last spoke.\n\n"
        "I am writing to share that AgencyIQ has developed some exciting enhancements from both a content "
        "and product perspective. We are circulating our product roadmap with our current clients and wanted "
        "to include {account} in those conversations given your earlier interest in our platform.\n\n"
        "Pending your interest, we'd be thrilled to get your perspective as we prioritize our future "
        "investments. If so, please let me know when you have half an hour to speak with us.\n\n"
        "Thanks!\n[Your Name]"
    ),
}

# Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track Re-Approach
# Script #2 ("Determining Interest") -- explicitly documented as "to be
# sent in follow-up to Re-approach Script #1." Lightly trimmed (dropped a
# claim about "FDA stakeholder bios" specific to the LS version, no food
# equivalent confirmed). Used for the SECOND consecutive stalled
# suggestion for the same account (see suggestion_history.py), regardless
# of which attempt-1 template actually fired -- the real library only
# documents a sequel for the pricing/terms line specifically, so this is
# a deliberate simplification, not a perfect content match to Script #3
# or the trial offer.
DETERMINING_INTEREST_TEMPLATE = {
    "id": "determining_interest",
    "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #2 (Determining Interest)",
    "subject": "Following up – still interested in reconnecting?",
    "body": (
        "{first_name} —\n\n"
        "I wanted to follow up here and make sure we're able to find time to connect if you're still interested "
        "in taking advantage of our updated terms and pricing. I know how valuable {account} found AgencyIQ's "
        "daily push content and in-depth food regulatory analysis.\n\n"
        "Is a call to discuss updated pricing of interest?\n\n"
        "Thanks,\n[Your Name]"
    ),
}

# Real script -- see MASTER_KEY_BD_Scripts.pdf, standalone "Breakup email"
# (already vertical-neutral in the source -- no LS/Food-specific wording
# to adapt). BDS_Best_Practices.pdf notes real policy reserves this for
# lower-tier contacts and keeps top-tier contacts in slow track instead --
# "tier" isn't in any export this pipeline parses (it's a by-hand 3x3
# judgment call), so this applies uniformly after enough unresolved
# attempts rather than trying to guess tier. Used from the THIRD
# consecutive stalled suggestion onward.
BREAKUP_TEMPLATE = {
    "id": "breakup",
    "source": "MASTER_KEY_BD_Scripts.pdf — Breakup Email",
    "subject": "Let's connect",
    "body": (
        "Hi {first_name},\n\n"
        "I hope you are having a great week. Over the past couple of months, I've shared several of our food "
        "regulatory analyses with you and I hope you found them helpful. To ensure you continue receiving "
        "valuable insights, I'd love to discuss how our platform can support {account}'s needs more "
        "effectively.\n\n"
        "I would like to offer your team a complimentary trial of our services. It will provide you with full "
        "access to our in-depth food regulatory analyses and updates, allowing you to discover the full range "
        "of our content for yourself. Could we schedule a brief meeting to explore this further? Please let me "
        "know a convenient time, and I'll arrange the details.\n\n"
        "Looking forward to connecting soon.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Consecutive stalled suggestions at or above this count get the breakup
# email instead of another re-approach/determining-interest cycle.
BREAKUP_ATTEMPT_THRESHOLD = 3


def _fill(template, first_name, account):
    return {
        "id": template["id"],
        "source": template["source"],
        "subject": template["subject"],
        "body": template["body"].format(first_name=first_name, account=account),
    }


def suggest_email_template(row):
    """row: a tracker.py row dict -- needs 'actionable_status', 'account',
    'contacts' (from campaign_parser.top_contacts), 'attended_webinar' /
    'subscribed_to_newsletter' (from campaign_parser.has_attended_webinar
    / has_subscribed_to_newsletter), 'examples' (from
    suggestions.suggest_reengagement_examples / revival_library.py --
    closed-won accounts whose own silence-then-revival pattern resembles
    this one), and 'stalled_attempt_count' (from suggestion_history.py,
    via run_tracker's optional --suggestion-history -- how many
    consecutive runs in a row this account has come back "stalled" with no
    resolution in between; absent/0/1 all mean "first attempt," so this
    stays backward compatible when history tracking isn't wired up) --
    all precomputed once in run_tracker.

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
    subscribed = row.get("subscribed_to_newsletter")
    attended = row.get("attended_webinar")

    if status == "stalled":
        attempt_count = row.get("stalled_attempt_count") or 1
        if attempt_count >= BREAKUP_ATTEMPT_THRESHOLD:
            # Enough unresolved cycles that continuing to re-approach
            # isn't working -- time for the real breakup script rather
            # than a fourth variation on "let's reconnect."
            template = BREAKUP_TEMPLATE
        elif attempt_count == 2:
            # One prior stalled suggestion already went unresolved --
            # this is its documented real sequel, not another first
            # attempt.
            template = DETERMINING_INTEREST_TEMPLATE
        elif subscribed and attended:
            # First attempt, proven engagement that still went dark --
            # the real scripts' own trial-offer trigger, and a stronger
            # card to play than a generic re-approach.
            template = TRIAL_OFFER_TEMPLATE
        elif row.get("examples"):
            # Only lean on "we've revived accounts like yours" when the
            # closed-won revival library actually backs that up for THIS
            # account.
            template = SLOW_TRACK_REAPPROACH_TEMPLATE
        else:
            template = SLOW_TRACK_PRODUCT_FEEDBACK_TEMPLATE
    elif not subscribed:
        template = NEWSLETTER_INVITE_TEMPLATE
    elif not attended:
        template = WEBINAR_INVITE_TEMPLATE
    else:
        # Proven engagement, but only cooling off (not yet stalled) --
        # an ordinary continuing touch. The bigger trial-offer incentive
        # is reserved for stalled (see above): the real breakup email only
        # extends a trial once a relationship is nearly lost, not this early.
        template = FOLLOWUP_SAMPLE_CONTENT_TEMPLATE

    return _fill(template, first_name, account)
