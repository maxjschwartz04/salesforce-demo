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
- Food and Life Sciences only, picked per account via row["vertical"]
  ("food" or "life_sciences", default "food" for backward compatibility --
  see tracker.py's account spec syntax). There's still no reliable
  per-account vertical field anywhere in the Salesforce exports this
  pipeline parses (checked: the Opportunity export has no
  industry/vertical column, and campaign-name vertical tags only cover a
  minority of engagement records), so this is a by-hand tag whoever runs
  the tool supplies per account, not something auto-detected. There's
  deliberately no separate "chemicals" vertical -- by team decision,
  chemicals accounts route through "life_sciences" rather than getting
  their own track (also handy since the source library only has real
  Chemicals content for the newsletter and webinar invites, nothing for
  the "stalled" escalation ladder).
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
  the account has subscribed to the vertical's newsletter or attended a
  webinar (see campaign_parser.has_subscribed_to_newsletter /
  has_attended_webinar) -- leading with the newsletter ask (lowest
  commitment) before a webinar invite, matching the order the real intro
  scripts themselves use. A cooling_off account that's already subscribed
  AND attended gets an ordinary content follow-up; a STALLED account in
  that same spot gets ANOTHER webinar invite rather than the free-trial
  script, deliberately -- see the comment on that branch in
  suggest_email_template for why (short version: the trial-offer script's
  real opening line asserts the newsletter subscribe was recent, which
  "subscribed" as a lifetime yes/no flag can't actually back up). The
  trial offer is reserved for attempt 2 on that track instead, once the
  gentler re-invite has already gone unanswered -- matching the real
  scripts' own late-stage framing for it ("Thanks for subscribing to FDA
  and EMA Today," the Food "thank you for subscribing" follow-up, and the
  breakup email all use it as a late-stage lever, not an early one).
  Within "stalled," the choice between that track and the two Slow Track
  Re-Approach scripts depends first on the proven-engagement signal, then
  on whether the closed-won revival library (revival_library.py /
  suggestions.py) has a real precedent for this account's silence -- see
  suggest_email_template. Current trial-usage status still isn't tracked
  (that data lives on Product Baskets, a different Salesforce object than
  anything in the exports this pipeline currently parses -- see
  BDS_Best_Practices.pdf), so this can offer a trial to someone already on
  one; a real, known limitation, same shape as the other gaps above.
- Escalation for repeatedly-"stalled" accounts (see suggestion_history.py
  and row["stalled_attempt_count"]): the webinar-invite track escalates to
  the trial offer (see above); the real library documents one other
  attempt-2 sequel script, Determining Interest, written specifically to
  follow the pricing-themed Slow Track Script #1 ("...taking advantage of
  our updated terms and pricing") -- so it only fires as attempt 2 when
  attempt 1 actually was that pricing script. The product-feedback
  attempt-1 track escalates to the real, content-agnostic Last-Ditch
  Effort script instead, since neither it nor Determining Interest fit.
  Nothing ever gets suggested twice in a row verbatim. Attempt 3+ always
  gets the breakup email, which is generic enough to follow any of the
  three tracks.

Usage:
    from email_templates import suggest_email_template
    suggest_email_template(row)  # row is a tracker.py row dict
"""

# Real script -- see AIQ_Outreach_Templates_1.pdf, Follow-up Script #7
# ("Last-Ditch Effort"). Already vertical-neutral in the source (never
# references what was said in any prior email), so used as-is for both
# verticals rather than adapted. This is what a repeatedly-"stalled"
# account gets as attempt 2 when attempt 1 wasn't the pricing-themed Slow
# Track Re-Approach script (see module docstring) -- real and distinct
# from both the attempt-1 script and the eventual breakup email, so nothing
# repeats verbatim across an escalation.
LAST_DITCH_EFFORT_TEMPLATE = {
    "id": "last_ditch_effort",
    "source": "AIQ_Outreach_Templates_1.pdf — Follow-up Script #7 (Last-Ditch Effort)",
    "subject": "Partner, not pester",
    "body": (
        "{first_name},\n\n"
        "My goal is to partner, not pester. Having not heard back from you, am I right to assume you're no "
        "longer interested in speaking with AgencyIQ?\n\n"
        "If I'm mistaken, let's find some time for you to connect with our head of product to hear how we're "
        "supporting your regulatory intelligence peers with our platform.\n\n"
        "Either way, thanks for letting me know.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Real script -- see MASTER_KEY_BD_Scripts.pdf, standalone "Breakup email."
# Already vertical-neutral in the source (no LS/Food-specific wording at
# all -- checked directly against the PDF text, not assumed), so used as-is
# for both verticals. BDS_Best_Practices.pdf notes real policy reserves
# this for lower-tier contacts and keeps top-tier contacts in slow track
# instead -- "tier" isn't in any export this pipeline parses (it's a
# by-hand 3x3 judgment call), so this applies uniformly after enough
# unresolved attempts rather than trying to guess tier. Used from the
# THIRD consecutive stalled suggestion onward, any track.
BREAKUP_TEMPLATE = {
    "id": "breakup",
    "source": "MASTER_KEY_BD_Scripts.pdf — Breakup Email",
    "subject": "Let's connect",
    "body": (
        "Hi {first_name},\n\n"
        "I hope you are having a great week. Over the past couple of months, I've shared several of our "
        "regulatory analyses with you and I hope you found them helpful. To ensure you continue receiving "
        "valuable insights, I'd love to discuss how our platform can support {account}'s needs more "
        "effectively.\n\n"
        "I would like to offer your team a complimentary trial of our services. It will provide you with full "
        "access to our in-depth regulatory analyses and updates, allowing you to discover the full range "
        "of our content for yourself. Could we schedule a brief meeting to explore this further? Please let me "
        "know a convenient time, and I'll arrange the details.\n\n"
        "Looking forward to connecting soon.\n\n"
        "Best,\n[Your Name]"
    ),
}

# Consecutive stalled suggestions at or above this count get the breakup
# email instead of another re-approach/escalation cycle.
BREAKUP_ATTEMPT_THRESHOLD = 3

FOOD_TEMPLATES = {
    # Real script -- see AgencyIQ_Email_Templates_2.pdf, "3. Food
    # Newsletter Invite," lightly trimmed to the parts we can fill from
    # real data (the source script also pastes in a real recent edition,
    # which this tool can't fabricate).
    "newsletter_invite": {
        "id": "newsletter_invite",
        "source": "AgencyIQ_Email_Templates_2.pdf — Food Newsletter Invite",
        "subject": "FDA Today: Food – Clear, Expert Insights for Food Regulatory Professionals",
        "body": (
            "Hi {first_name},\n\n"
            "Based on your role at {account}, I thought it might be useful to share a resource many food "
            "regulatory professionals use to stay current.\n\n"
            "AgencyIQ publishes a newsletter by regulatory specialists focused on food policy and oversight. It "
            "covers FDA and USDA developments, state-level actions, and emerging compliance considerations, all "
            "designed to help teams anticipate changes and prioritize what matters most.\n\n"
            "You can opt in to receive future issues if it aligns with your work by subscribing here.\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see MASTER_KEY_BD_Scripts.pdf, "Webinar Invite"
    # (Chemicals section). The real library uses this identical structure
    # across verticals with just the industry noun swapped (the same
    # pattern the real Newsletter Invite and "Congratulations on your new
    # role" scripts use for their own LS/Food variants), so this
    # substitutes "food" for "chemicals" rather than inventing new
    # wording. BDS_Best_Practices.pdf says invites should go out roughly a
    # week ahead of the date.
    "webinar_invite": {
        "id": "webinar_invite",
        "source": "MASTER_KEY_BD_Scripts.pdf — Webinar Invite (Food adaptation)",
        "subject": "AgencyIQ Webinar Invite",
        "body": (
            "Hi {first_name},\n\n"
            "Staying ahead of the curve on food regulatory policy has become much less predictable. That's why "
            "I wanted to personally invite you to AgencyIQ's upcoming webinar at [DATE & TIME], titled "
            "[WEBINAR TITLE].\n\n"
            "Our food regulatory team will review recent developments relevant to {account} and take your "
            "questions live.\n\n"
            "You can sign up here: [LINK]\n\n"
            "All the best,\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf's "Sample Content"
    # follow-up, adapted with the food-specific content-share pattern from
    # the real "FDA Revokes 52 Food Standards" example (Food scripts,
    # MASTER_KEY BD Scripts) rather than the source's "[topic/therapeutic
    # area]" LS framing. For an account that already has the newsletter
    # and has attended a webinar but hasn't reached the trial-ready bar yet.
    "followup_sample_content": {
        "id": "followup_sample_content",
        "source": "AIQ_Outreach_Templates_1.pdf — Follow-up Script #2 (Sample Content, Food adaptation)",
        "subject": "Is a recent FDA or USDA food policy change impacting your regulatory strategy?",
        "body": (
            "{first_name} —\n\n"
            "I was wondering if a recent food regulatory development has been driving changes in strategy at "
            "{account}.\n\n"
            "If so, I'm writing to see if you have 30 minutes to connect this [day of week] at [time] to hear "
            "how AgencyIQ's food regulatory research and monitoring can support your team.\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see MASTER_KEY_BD_Scripts.pdf, Food Scripts section,
    # "Thank you for subscribing to FDA Today: Food!" -- genuinely
    # Food-native (not adapted from the LS version), using its own real
    # trial mechanism ("guest access for 3-4 weeks") rather than borrowing
    # the LS trial's wording. The real library only extends this once
    # someone's shown real engagement (subscribed AND attended a webinar
    # here) -- never as a first move.
    "trial_offer": {
        "id": "trial_offer",
        "source": "MASTER_KEY_BD_Scripts.pdf — Thank You for Subscribing to FDA Today: Food",
        "subject": "Thank You for Subscribing to FDA Today: Food",
        "body": (
            "Hi {first_name},\n\n"
            "Thank you for subscribing to FDA Today: Food! Let me know if you've had any trouble receiving or "
            "reading it since you signed up and I'd be happy to troubleshoot.\n\n"
            "Our team works to provide a lot more than a twice-weekly newsletter, with analyses published by "
            "our researchers every week. If you like our newsletter after reading a few, we'd be happy to show "
            "you what resources and tools {account} would have access to on our platform with guest access for "
            "3-4 weeks.\n\n"
            "Are there any current projects you're focused on where we could share deeper analysis?\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track
    # Re-Approach Script #1 ("Updated Pricing and Terms"), adapted (no LS
    # or Food version of this section exists in the source library --
    # only Life Sciences). This section exists for exactly this
    # situation: an established relationship that's gone quiet. Use it
    # when the revival library (revival_library.py / suggestions.py)
    # actually has a closed-won account that came back from a similar
    # silence, i.e. there's real precedent to imply that with. The real
    # script explicitly raises a pricing/terms update as its reason for
    # reaching out ("We've also made updates to our pricing model...
    # worthwhile to discuss the fees") -- kept here (generalized, since
    # the source's own pricing mention is tied to a specific real client's
    # objection this tool can't fabricate a Food equivalent for) because
    # Script #2 (Determining Interest) is only a real, accurate sequel to
    # THIS script when it actually mentioned pricing.
    "slow_track_reapproach": {
        "id": "slow_track_reapproach",
        "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #1 (Food adaptation)",
        "subject": "AgencyIQ Updates – time to connect?",
        "body": (
            "{first_name},\n\n"
            "It's been a while — how are you?\n\n"
            "I thought it timely for us to reconnect on the AgencyIQ platform at {account}. We've seen several "
            "new platform releases and enhanced FDA coverage since we last spoke, and we've also made updates "
            "to our pricing and terms.\n\n"
            "If you still think our resources would be valuable, I think it'd be worthwhile to have a quick "
            "discussion around the details. Let me know what you think.\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track
    # Re-Approach Script #3 ("Requesting Assistance in Future of
    # Product"), adapted (LS-only in the source). Doesn't lean on "we've
    # seen this pattern before" the way Script #1 does -- asks for
    # product feedback instead. Used when the revival library has no
    # comparable closed-won precedent for this account's silence, so
    # there's nothing real to back up a "we've revived accounts like
    # yours" framing.
    "slow_track_product_feedback": {
        "id": "slow_track_product_feedback",
        "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #3 (Food adaptation)",
        "subject": "AgencyIQ Product Roadmap – your assistance?",
        "body": (
            "{first_name},\n\n"
            "I hope you've all been well since we last spoke.\n\n"
            "I am writing to share that AgencyIQ has developed some exciting enhancements from both a content "
            "and product perspective. We are circulating our product roadmap with our current clients and "
            "wanted to include {account} in those conversations given your earlier interest in our platform.\n\n"
            "Pending your interest, we'd be thrilled to get your perspective as we prioritize our future "
            "investments. If so, please let me know when you have half an hour to speak with us.\n\n"
            "Thanks!\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track
    # Re-Approach Script #2 ("Determining Interest"), adapted (LS-only in
    # the source -- explicitly documented there as "to be sent in
    # follow-up to Re-approach Script #1"). Only used here when attempt 1
    # actually was slow_track_reapproach above (see suggest_email_template)
    # -- this script presupposes a pricing conversation was already
    # raised, so it isn't a safe stand-in for the trial-offer or
    # product-feedback tracks, which never mention pricing.
    "determining_interest": {
        "id": "determining_interest",
        "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #2 (Determining Interest, Food adaptation)",
        "subject": "Following up – still interested in reconnecting?",
        "body": (
            "{first_name} —\n\n"
            "I wanted to follow up here and make sure we're able to find time to connect if you're still "
            "interested in taking advantage of our updated terms and pricing. I know how valuable {account} "
            "found AgencyIQ's daily push content and in-depth food regulatory analysis.\n\n"
            "Is a call to discuss updated pricing of interest?\n\n"
            "Thanks,\n[Your Name]"
        ),
    },
}

LIFE_SCIENCES_TEMPLATES = {
    # Real script -- see AgencyIQ_Email_Templates_2.pdf, "4. Newsletter
    # Invite – LS," used close to verbatim (already vertical-native).
    "newsletter_invite": {
        "id": "newsletter_invite",
        "source": "AgencyIQ_Email_Templates_2.pdf — Newsletter Invite (Life Sciences)",
        "subject": "AgencyIQ | Regulatory Insights",
        "body": (
            "Hi {first_name},\n\n"
            "I'm reaching out from AgencyIQ (POLITICO's life sciences regulatory division) with a resource I "
            "thought might be helpful in your role at {account}. Our free regulatory newsletter, FDA Today, "
            "provides a quick, weekly roundup of key developments from the FDA.\n\n"
            "It's published multiple times a week and packed with regulatory intelligence from our research "
            "team's daily scanning.\n\n"
            "Hope it saves time and helps with planning ahead.\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see MASTER_KEY_BD_Scripts.pdf, "Webinar Invite"
    # (Chemicals section) -- same reusable cross-vertical structure the
    # Food version above is built from (see that entry's comment), here
    # with "life sciences" swapped in instead of "food."
    "webinar_invite": {
        "id": "webinar_invite",
        "source": "MASTER_KEY_BD_Scripts.pdf — Webinar Invite (Life Sciences adaptation)",
        "subject": "AgencyIQ Webinar Invite",
        "body": (
            "Hi {first_name},\n\n"
            "Staying ahead of the curve on life sciences regulatory policy has become much less predictable. "
            "That's why I wanted to personally invite you to AgencyIQ's upcoming webinar at [DATE & TIME], "
            "titled [WEBINAR TITLE].\n\n"
            "Our life sciences regulatory team will review recent developments relevant to {account} and take "
            "your questions live.\n\n"
            "You can sign up here: [LINK]\n\n"
            "All the best,\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Follow-up Script #2
    # ("Sample Content") -- this is the vertical the source library was
    # actually written for, so used close to verbatim. The source itself
    # leaves "[topic/therapeutic area]" open rather than naming a specific
    # real example (unlike the Food version, which had a real example to
    # borrow from MASTER_KEY_BD_Scripts.pdf) -- left as a bracket here too,
    # same rule as every other source-left blank in this file.
    "followup_sample_content": {
        "id": "followup_sample_content",
        "source": "AIQ_Outreach_Templates_1.pdf — Follow-up Script #2 (Sample Content)",
        "subject": "Is shifting FDA policy on [topic/therapeutic area] impacting your regulatory strategy?",
        "body": (
            "{first_name} —\n\n"
            "I was wondering if shifting FDA guidance and policy has been driving frequent changes in strategy "
            "at {account}.\n\n"
            "If so, I'm writing to see if you have 30 minutes to connect this [day of week] at [time] to hear "
            "how AgencyIQ's research and monitoring on [topic/therapeutic area] can support your team.\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see MASTER_KEY_BD_Scripts.pdf, "Thanks for
    # subscribing to EMA and FDA Today," trimmed to the parts we can fill
    # from real data (the source also pastes in specific real analyses and
    # names a specific real client this tool can't fabricate an equivalent
    # for). The real library only extends a trial offer once someone's
    # shown real engagement -- never as a first move.
    "trial_offer": {
        "id": "trial_offer",
        "source": "MASTER_KEY_BD_Scripts.pdf — Thanks for Subscribing to EMA and FDA Today",
        "subject": "More from AgencyIQ, Beyond FDA and EMA Today",
        "body": (
            "Hi {first_name},\n\n"
            "Thanks for subscribing to AgencyIQ's FDA and EMA Today newsletters.\n\n"
            "These updates are a great way to stay informed, but they represent just a fraction of the "
            "regulatory intelligence our team produces each week for companies like {account}.\n\n"
            "If it would help, I'd be happy to set you up with a complimentary trial login to explore more of "
            "our in-depth coverage.\n\n"
            "Are there any current projects or regulatory areas you're focused on where we could share deeper "
            "analysis?\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track
    # Re-Approach Script #1 ("Updated Pricing and Terms") -- the vertical
    # this section was actually written for, so used close to verbatim
    # (trimmed a name-dropped real client's specific pricing objection,
    # which doesn't apply to whoever this is actually sent to). Keeps the
    # real pricing/terms mention -- Script #2 (Determining Interest) below
    # is only an accurate sequel to this one because it does.
    "slow_track_reapproach": {
        "id": "slow_track_reapproach",
        "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #1",
        "subject": "AgencyIQ Updates – time to connect?",
        "body": (
            "{first_name},\n\n"
            "It's been a while — how are you?\n\n"
            "I thought it timely for us to reconnect on the AgencyIQ platform at {account}. Since we spoke, "
            "we've seen several new platform releases (including new customizations and push content) as well "
            "as enhanced FDA coverage. We've also made updates to our pricing model.\n\n"
            "If you still think our resources would be valuable, I think it'd be worthwhile for us to have a "
            "quick discussion around the fees. Let me know what you think.\n\n"
            "Best,\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track
    # Re-Approach Script #3 ("Requesting Assistance in Future of
    # Product") -- the vertical this section was actually written for, so
    # used close to verbatim (trimmed the name-dropped real clients, e.g.
    # "Regeneron, BD, Gilead, Roche," which don't apply to a new prospect).
    "slow_track_product_feedback": {
        "id": "slow_track_product_feedback",
        "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #3",
        "subject": "AgencyIQ Product Roadmap – your assistance?",
        "body": (
            "{first_name},\n\n"
            "I hope you've all been well since we last spoke.\n\n"
            "I am writing to share that AgencyIQ has developed some exciting enhancements from both a content "
            "and product perspective. We are circulating our product roadmap with our current clients and "
            "wanted to include {account} in those conversations given your earlier interest in our platform.\n\n"
            "Pending your interest, we'd be thrilled to get your perspective as we prioritize our future "
            "investments. If so, please let me know when you have half an hour to speak with us.\n\n"
            "Thanks!\n[Your Name]"
        ),
    },
    # Real script -- see AIQ_Outreach_Templates_1.pdf, Slow Track
    # Re-Approach Script #2 ("Determining Interest") -- explicitly
    # documented there as "to be sent in follow-up to Re-approach Script
    # #1," used close to verbatim including its real content specifics
    # ("daily push content," "guidance and proposed rules," "FDA
    # stakeholder bios" -- all real LS-appropriate claims, not fabricated).
    # Only used when attempt 1 actually was slow_track_reapproach above
    # (see suggest_email_template).
    "determining_interest": {
        "id": "determining_interest",
        "source": "AIQ_Outreach_Templates_1.pdf — Slow Track Re-Approach Script #2 (Determining Interest)",
        "subject": "Following up – still interested in reconnecting?",
        "body": (
            "{first_name} —\n\n"
            "I wanted to follow up here and ensure we were able to find time to connect soon if you're "
            "interested in taking advantage of our updated terms and pricing. I know how valuable {account} has "
            "found AgencyIQ's daily push content, in-depth analysis on guidance and proposed rules, and FDA "
            "stakeholder bios.\n\n"
            "Is a call to discuss updated pricing of interest?\n\n"
            "Thanks,\n[Your Name]"
        ),
    },
}

TEMPLATE_LIBRARIES = {
    "food": FOOD_TEMPLATES,
    "life_sciences": LIFE_SCIENCES_TEMPLATES,
}


def _fill(template, first_name, account, vertical):
    return {
        "id": template["id"],
        "vertical": vertical,
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
    this one), 'stalled_attempt_count' (from suggestion_history.py, via
    run_tracker's optional --suggestion-history -- how many consecutive
    runs in a row this account has come back "stalled" with no resolution
    in between; absent/0/1 all mean "first attempt," so this stays
    backward compatible when history tracking isn't wired up), and
    'vertical' ("food" or "life_sciences" -- defaults to "food" if absent,
    also backward compatible) -- all precomputed once in run_tracker.

    Returns None for "new"/"on_pace"/anything else -- there's nothing to
    suggest sending. Otherwise returns {id, vertical, source, subject,
    body} with the real template's fillable blanks completed from real
    data; blanks the SOURCE script itself leaves open ([topic], [DATE &
    TIME], etc.) are left as-is for a rep to complete, same as the source
    material expects."""
    status = row.get("actionable_status")
    if status not in ("never_engaged", "cooling_off", "stalled"):
        return None

    contacts = row.get("contacts") or []
    first_name = contacts[0].get("first_name") or "there" if contacts else "there"
    account = row.get("account") or "your organization"
    subscribed = row.get("subscribed_to_newsletter")
    attended = row.get("attended_webinar")
    vertical = row.get("vertical") or "food"
    templates = TEMPLATE_LIBRARIES.get(vertical, FOOD_TEMPLATES)

    if status == "stalled":
        attempt_count = row.get("stalled_attempt_count") or 1
        # What attempt 1 was/would be, regardless of the CURRENT attempt --
        # decides both the attempt-1 email itself and, for attempt 2, which
        # real escalation script is an accurate sequel to it.
        if subscribed and attended:
            # NOT trial_offer here, deliberately: that script's real
            # opening line ("Thank you for subscribing... since you signed
            # up") asserts the subscribe was recent, but "subscribed" is a
            # lifetime yes/no flag with no date attached (no subscribe-date
            # field exists in any export this pipeline parses) -- it could
            # just as easily have happened months ago. A stalled account
            # getting "thanks for JUST subscribing" reads as out of touch
            # regardless of whether that claim happens to be true. The
            # webinar invite makes no claim about the past at all --
            # purely forward-looking ("upcoming webinar") -- so it's safe
            # to lead with regardless of how long ago they actually
            # engaged, while still reflecting that they're a genuinely
            # engaged contact, not a cold one.
            attempt_1_template = templates["webinar_invite"]
        elif row.get("examples"):
            attempt_1_template = templates["slow_track_reapproach"]
        else:
            attempt_1_template = templates["slow_track_product_feedback"]

        if attempt_count >= BREAKUP_ATTEMPT_THRESHOLD:
            # Enough unresolved cycles that continuing to re-approach
            # isn't working -- time for the real breakup script rather
            # than a third variation on "let's reconnect."
            template = BREAKUP_TEMPLATE
        elif attempt_count == 2:
            if attempt_1_template["id"] == "webinar_invite":
                # The gentle re-invite didn't land -- now lean on the
                # stronger, proven-engagement incentive (real script,
                # reserved for exactly this point in the real library:
                # "only extend a trial once a relationship is nearly
                # lost," not as a first move).
                template = templates["trial_offer"]
            elif attempt_1_template["id"] == "slow_track_reapproach":
                # Attempt 1 raised pricing -- this is its documented real
                # sequel.
                template = templates["determining_interest"]
            else:
                # Attempt 1 was product feedback, which never raised
                # pricing, so Determining Interest would reference a
                # conversation that never happened. Fall back to the real,
                # content-agnostic Last-Ditch Effort script instead of
                # repeating attempt 1 verbatim.
                template = LAST_DITCH_EFFORT_TEMPLATE
        else:
            template = attempt_1_template
    elif not subscribed:
        template = templates["newsletter_invite"]
    elif not attended:
        template = templates["webinar_invite"]
    else:
        # Proven engagement, but only cooling off (not yet stalled) --
        # an ordinary continuing touch. The bigger trial-offer incentive
        # is reserved for stalled (see above): the real breakup email only
        # extends a trial once a relationship is nearly lost, not this early.
        template = templates["followup_sample_content"]

    return _fill(template, first_name, account, vertical)
