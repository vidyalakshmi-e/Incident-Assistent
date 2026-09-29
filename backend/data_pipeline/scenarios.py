"""Scenario catalog for *conditioned* synthetic text generation (DATASET Step 4).

Source B (the structured event log) has no description or resolution text. For a stratified
sample of its real rows, text is generated conditioned on that row's real fields:

* CI_Subcat          → which scenarios are compatible (a SAN incident never gets a VPN story)
* Closure_Code       → scenario eligibility and which resolution strategy is chosen
* No_of_Reassignments→ strategy choice (quick workaround vs. escalated/engineering fix)
* Impact / Urgency   → how the affected scope and urgency are phrased
* Related_Change     → raises the prior for change-related scenarios
* CI_Name            → the real configuration item is named in the text

The catalog deliberately seeds the variety the downstream features need:
* several *symptom views* per scenario (user / monitoring / engineer wording) that share one
  root cause → something real for Pattern Intelligence to discover
* 2–3 genuinely different resolution strategies per scenario → Resolution Strategy Intelligence
* low-quality vs. detailed notes (decided in synthetic.py) → Knowledge Quality Manager

The scenario/strategy ids a row was generated from are stored as `gt_*` columns. They are ground
truth for evaluation only and are never read by runtime features.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy:
    id: str
    label: str
    steps: list[str]
    notes: list[str]  # detailed resolution-note templates (engineer voice)
    closure_affinity: dict[str, float] = field(default_factory=dict)
    reassign_bias: str = "any"  # "low" = quick fix, "high" = escalated/engineering fix
    destructive: bool = False


@dataclass
class Scenario:
    id: str
    name: str
    ci_groups: list[str]
    closure_codes: dict[str, float]
    component: str
    services: list[str]
    dependency: str
    root_cause: str
    failure_type: str
    triggers: list[str]  # "" = gradual / no trigger stated
    titles: list[str]
    views: dict[str, list[str]]
    strategies: list[Strategy]
    change_affinity: float = 1.0  # prior multiplier when the real row has a Related_Change
    ci_subcats: list[str] | None = None  # optional finer CI_Subcat restriction within ci_groups
    device_scope: bool = False  # single-device CIs: scope is phrased per device, not per service
    env_applicable: bool = True  # whether an environment (production/acceptance) can be mentioned


APP_SERVICES = [
    "Internet Banking portal", "mortgage advisory application", "CRM client-records system",
    "payments processing service", "branch teller application", "loan origination system",
    "document management system", "HR self-service portal", "risk reporting dashboard",
    "customer onboarding portal",
]
APP_GROUPS = ["app_server", "app_web", "app_desktop"]
FAULT_CODES = {"Software": 3.0, "Other": 1.5, "Unknown": 1.0}

SCENARIOS: list[Scenario] = [
    # ------------------------------------------------------------------ application
    Scenario(
        id="APP-MEMLEAK",
        name="Application memory leak causing progressive slowdown and freezes",
        ci_groups=APP_GROUPS, closure_codes=FAULT_CODES,
        component="Application server", services=APP_SERVICES,
        dependency="JVM heap / session cache",
        root_cause="memory leak in the application's session cache exhausting the heap",
        failure_type="performance degradation",
        triggers=["", "", "after a period of high usage at month-end"],
        titles=["{service} slow and freezing", "Application hangs when opening records",
                "Slow response times on {ci}", "{service} becomes unresponsive"],
        views={
            "user": [
                "The {service} gets slower during the day and freezes when we try to open client records. Restarting it helps for a while.",
                "Opening a record in the {service} takes minutes and sometimes the screen freezes completely. After a restart it works again but the slowness comes back.",
                "Everything in the {service} is very sluggish, basic screens take forever to load and it hangs regularly.",
            ],
            "monitoring": [
                "Monitoring alert on {ci}: heap usage above 95% and average response time over 8 seconds for the {service}.",
                "Response-time alarm for {ci}: transactions degrade steadily after each restart until the application stops responding.",
            ],
            "engineer": [
                "Long garbage-collection pauses observed on {ci}; old-gen heap keeps growing between restarts and the {service} freezes.",
                "Thread dumps from {ci} show threads blocked in GC; memory usage climbs continuously until the {service} hangs.",
            ],
        },
        strategies=[
            Strategy("restart_service", "Restart / recycle the application service (temporary workaround)",
                     ["Recycle the application service on the affected node", "Verify heap usage returns to baseline",
                      "Monitor response times for recurrence"],
                     ["Heap on {ci} was almost exhausted. Recycled the application service during a quiet window; response times back to normal. Workaround only, leak still present.",
                      "Restarted the {service} application pool on {ci}. Memory usage dropped from 96% to 40% and users confirmed screens load again."],
                     {"Other": 2, "Unknown": 2, "Software": 0.7}, reassign_bias="low"),
            Strategy("vendor_patch", "Apply the vendor fix for the session-cache memory leak",
                     ["Confirm the leak with a heap dump", "Install the vendor patch that fixes the session-cache leak",
                      "Restart and monitor heap growth for 48 hours"],
                     ["Heap dump analysis on {ci} showed the session cache never releasing objects. Vendor supplied a patch for the leak; installed it and heap usage stays flat after 48h of monitoring.",
                      "Root cause: memory leak in the session cache of the {service}. Deployed the supplier hotfix via change, restarted, and verified no heap growth over two days."],
                     {"Software": 3}, reassign_bias="high"),
            Strategy("tune_heap", "Increase heap size and tune GC / cache eviction settings",
                     ["Increase the maximum heap size", "Set a cache eviction limit for the session cache",
                      "Restart and confirm GC pauses are below one second"],
                     ["Increased max heap on {ci} and configured an eviction limit on the session cache. GC pauses reduced from ~12s to under 1s; {service} stable since.",
                      "Tuned JVM settings (larger heap, G1 GC) and capped the session cache size for the {service}. Freezes no longer reproduced."],
                     {"Software": 1.5, "Other": 1}, reassign_bias="any"),
        ],
    ),
    Scenario(
        id="APP-CONNPOOL",
        name="Database connection pool exhaustion in the application tier",
        ci_groups=APP_GROUPS, closure_codes=FAULT_CODES,
        component="Application server", services=APP_SERVICES,
        dependency="Oracle database connection pool",
        root_cause="the application's database connection pool is exhausted because connections are not returned",
        failure_type="intermittent failure",
        triggers=["", "during peak business hours", "after traffic increased at the start of the month"],
        titles=["Timeouts in {service}", "Intermittent errors in {service} under load",
                "{service}: cannot obtain database connection"],
        views={
            "user": [
                "The {service} regularly shows an error page saying the request timed out, mostly in the morning when everyone is working.",
                "Saving data in the {service} fails intermittently with a generic error; after a few minutes it works again.",
            ],
            "monitoring": [
                "Error-rate alert for {ci}: 15% of requests to the {service} fail with timeout errors during peak hours.",
                "Log monitoring on {ci} reports 'Timeout waiting for idle object' exceptions for the {service}.",
            ],
            "engineer": [
                "Application logs on {ci} show 'Cannot get a connection, pool exhausted'; all pool connections are in use and new requests wait until they time out.",
                "Active DB connections from {ci} stuck at the pool maximum; requests queue and the {service} returns timeouts.",
            ],
        },
        strategies=[
            Strategy("increase_pool", "Increase the connection pool size and timeouts",
                     ["Check current pool utilisation", "Increase max pool size within database limits",
                      "Monitor error rate during the next peak"],
                     ["Pool for the {service} on {ci} was capped at 50 connections and fully used at peak. Raised the maximum to 120 after DBA approval; no timeouts during the next peak.",
                      "Increased connection pool size and idle timeout on {ci}. Error rate dropped to zero."],
                     {"Other": 1.5, "Unknown": 1.5, "Software": 1}, reassign_bias="low"),
            Strategy("fix_connection_leak", "Fix the connection leak in the application code",
                     ["Enable pool leak detection logging", "Identify the code path that does not close connections",
                      "Deploy the code fix and verify connections are returned"],
                     ["Leak detection on {ci} pointed to the export function not closing its DB connection. Development delivered a fix; after deployment pool usage stays below 30%.",
                      "Root cause was a missing connection close in a batch call of the {service}. Hotfix deployed via change; pool no longer exhausts."],
                     {"Software": 3}, reassign_bias="high"),
            Strategy("restart_app_server", "Restart the application server to release connections",
                     ["Restart the application server", "Confirm connections are released", "Monitor for recurrence"],
                     ["Restarted the application server on {ci}, which released all stuck connections. {service} available again; problem ticket raised for structural fix.",
                      "All connections were hanging; restart of {ci} cleared the pool. Users can work again."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
        ],
    ),
    Scenario(
        id="APP-RELEASE-REGRESSION",
        name="Defect introduced by a new application release",
        ci_groups=APP_GROUPS, closure_codes={"Software": 3.0, "Other": 1.0},
        component="Application", services=APP_SERVICES,
        dependency="release pipeline",
        root_cause="a defect introduced by the latest application release",
        failure_type="functional failure",
        triggers=["after the weekend release", "since the new version was deployed", "after last night's deployment"],
        titles=["Function broken after release in {service}", "{service}: error since new version",
                "Button does nothing after update of {service}"],
        views={
            "user": [
                "Since the new version of the {service} was installed, the 'submit' button does nothing and we cannot finish our work.",
                "After the update of the {service} we get an error message when printing the overview; this worked fine last week.",
            ],
            "monitoring": [
                "Synthetic transaction for the {service} on {ci} fails at step 3 since the latest deployment.",
            ],
            "engineer": [
                "Stack trace on {ci} shows a NullPointerException in the new validation module introduced with the latest release of the {service}.",
                "Regression in the {service}: the API call changed its payload in the new release and the frontend on {ci} cannot parse it.",
            ],
        },
        strategies=[
            Strategy("rollback_release", "Roll back to the previous release",
                     ["Confirm the defect is caused by the new release", "Roll back to the previous version via the release pipeline",
                      "Verify the function works and inform users"],
                     ["Defect confirmed in the new build of the {service}. Rolled {ci} back to the previous release via emergency change; function works again.",
                      "Release rolled back on {ci}. Users confirmed the submit function works. Fix will be included in the next release."],
                     {"Software": 1.5, "Other": 1.5}, reassign_bias="low"),
            Strategy("hotfix", "Deploy a hotfix for the defect",
                     ["Reproduce the defect in test", "Build and test a hotfix", "Deploy the hotfix via emergency change"],
                     ["Development reproduced the regression and built a hotfix for the validation module. Deployed on {ci} via emergency change; verified by key users.",
                      "Hotfix for the {service} deployed after testing in acceptance. Error no longer occurs."],
                     {"Software": 3}, reassign_bias="high"),
            Strategy("disable_feature_flag", "Disable the new feature via its feature toggle",
                     ["Identify the feature toggle for the new function", "Disable the toggle", "Verify the old behaviour is restored"],
                     ["New functionality disabled via feature toggle on {ci}; users fall back to the old screen until the fix is released.",
                      "Switched off the feature flag for the new print overview in the {service}. Workaround confirmed by users."],
                     {"Software": 1, "Other": 1}, reassign_bias="any"),
        ],
        change_affinity=4.0,
    ),
    Scenario(
        id="APP-SSO-AUTH",
        name="Single sign-on / authentication failures",
        ci_groups=APP_GROUPS + ["citrix_vdi"], closure_codes=FAULT_CODES,
        component="Authentication service", services=APP_SERVICES,
        dependency="identity provider (ADFS) / Active Directory",
        root_cause="the SSO trust between the application and the identity provider is broken (expired token-signing certificate or stale directory sync)",
        failure_type="hard failure",
        triggers=["", "after the identity-provider certificate rollover", "since this morning"],
        titles=["Users cannot log in to {service}", "Login loop in {service}", "SSO error on {service}"],
        views={
            "user": [
                "Nobody can log in to the {service}; after entering credentials we are sent back to the login page.",
                "I get 'access denied' when opening the {service} although I could log in yesterday.",
            ],
            "monitoring": [
                "Authentication failures for the {service} on {ci} jumped to 100% at 07:30.",
            ],
            "engineer": [
                "SAML responses for the {service} on {ci} are rejected with 'invalid signature'; the IdP token-signing certificate does not match the one configured.",
                "Kerberos/SSO handshake for the {service} fails on {ci}; the application cannot validate tokens from ADFS.",
            ],
        },
        strategies=[
            Strategy("update_idp_certificate", "Update the IdP token-signing certificate in the application",
                     ["Compare the IdP signing certificate with the application's trust store", "Import the new token-signing certificate",
                      "Test login with a pilot user"],
                     ["The ADFS token-signing certificate had rolled over but the {service} still trusted the old one. Imported the new certificate on {ci}; logins work.",
                      "Updated federation metadata for the {service} with the new signing certificate. SSO restored for all users."],
                     {"Software": 2, "Other": 1}, reassign_bias="high"),
            Strategy("resync_directory", "Re-synchronise directory accounts / group membership",
                     ["Check the user's group membership in AD", "Force directory synchronisation", "Ask the user to log in again"],
                     ["User was missing from the application access group after the nightly sync failed. Forced AD sync; access restored.",
                      "Directory sync for the {service} was stuck; restarted the sync job and group memberships were updated. Users can log in."],
                     {"Other": 2, "Unknown": 1.5}, reassign_bias="low"),
            Strategy("clear_sessions", "Clear cached sessions and browser tokens",
                     ["Clear the application's session store", "Ask users to clear browser cookies", "Verify login"],
                     ["Cleared stale sessions on {ci} and asked users to clear cookies; login loop resolved.",
                      "Session store on {ci} held invalid tokens. Flushed it; users can log in again."],
                     {"Other": 1.5, "Unknown": 1.5}, reassign_bias="low"),
        ],
    ),
    Scenario(
        id="APP-BATCH-INTERFACE",
        name="Nightly batch / interface job failure",
        ci_groups=["app_server", "app_web", "sap"], closure_codes={"Software": 2.0, "Data": 2.0, "Other": 1.5, "Unknown": 1.0},
        component="Batch scheduler", services=APP_SERVICES,
        dependency="upstream interface file delivery",
        root_cause="the nightly batch job aborted because the upstream interface file was missing or malformed",
        failure_type="hard failure",
        triggers=["during the nightly run", "after the upstream system changed its export"],
        titles=["Nightly job failed for {service}", "No data in {service} this morning", "Interface error on {ci}"],
        views={
            "user": [
                "This morning the {service} shows yesterday's figures; the overnight update did not happen.",
                "Reports in the {service} are empty today, it looks like the data was not loaded.",
            ],
            "monitoring": [
                "Scheduler alert: job chain for the {service} on {ci} ended with return code 8 at 02:14.",
            ],
            "engineer": [
                "Batch job on {ci} aborted with 'input file not found'; the interface file from the upstream system did not arrive before the cut-off.",
                "Import job for the {service} failed on {ci}: record 1,204 of the interface file has an invalid date format.",
            ],
        },
        strategies=[
            Strategy("rerun_job", "Rerun the batch job after the input is available",
                     ["Check the job log for the failing step", "Confirm the input file is now present", "Restart the job from the failed step"],
                     ["Interface file arrived late. Restarted the job chain on {ci} from the failed step; data loaded by 09:10 and users informed.",
                      "Reran the import job after the file was delivered. {service} shows today's data."],
                     {"Other": 2, "Unknown": 2, "Software": 1}, reassign_bias="low"),
            Strategy("fix_input_file", "Correct the malformed interface file with the supplier and reload",
                     ["Identify the invalid records", "Have the upstream team redeliver a corrected file", "Reload and validate record counts"],
                     ["Upstream export contained invalid date formats after their change. Supplier redelivered a corrected file; reloaded and reconciled record counts.",
                      "Malformed records removed by the sending team and file redelivered; import successful on {ci}."],
                     {"Data": 3}, reassign_bias="high"),
            Strategy("adjust_schedule", "Adjust job dependencies / cut-off time in the scheduler",
                     ["Add a file-arrival dependency to the job", "Move the cut-off time", "Monitor the next nightly run"],
                     ["Added a file-watcher dependency so the job waits for the interface file instead of failing. Next nightly run completed.",
                      "Moved the job start from 02:00 to 03:30 in the scheduler to allow late delivery; no failures since."],
                     {"Software": 2}, reassign_bias="any"),
        ],
    ),
    Scenario(
        id="APP-DATA-QUALITY",
        name="Incorrect or corrupt data shown in the application",
        ci_groups=APP_GROUPS + ["sap"], closure_codes={"Data": 4.0, "Other": 1.0},
        component="Application data", services=APP_SERVICES,
        dependency="master data / import process",
        root_cause="incorrect records written by a faulty data import or manual update",
        failure_type="data integrity",
        triggers=["", "after a bulk import", "after a manual correction"],
        titles=["Wrong data in {service}", "Customer details incorrect in {service}", "Duplicate records in {service}"],
        views={
            "user": [
                "Client addresses in the {service} are wrong for a number of customers; letters are going to the old address.",
                "The {service} shows duplicate contracts for the same customer.",
            ],
            "monitoring": [
                "Data-quality check on {ci} reports 312 records failing referential integrity for the {service}.",
            ],
            "engineer": [
                "A bulk import on {ci} overwrote the address fields with values from the wrong column for part of the customer base.",
            ],
        },
        strategies=[
            Strategy("data_correction", "Correct the affected records with a validated correction script",
                     ["Identify the affected records", "Take a backup of the affected rows", "Run the reviewed correction script and verify"],
                     ["Identified 312 affected records. Took a backup of the rows, ran the reviewed correction script on {ci}, and the business verified a sample.",
                      "Corrected the wrong addresses using a validated script after backing up the table; verified with the data owner."],
                     {"Data": 3}, reassign_bias="any"),
            Strategy("restore_from_backup", "Restore the affected table from backup",
                     ["Determine the last good backup", "Get approval from the data owner", "Restore the table and re-apply valid changes"],
                     ["Import had corrupted the contract table. With data-owner approval restored it from the last good backup on {ci} and re-applied today's valid mutations.",
                      "Restored affected records from last night's backup; re-keyed the changes made since."],
                     {"Data": 1.5}, reassign_bias="high", destructive=True),
            Strategy("reprocess_feed", "Reprocess the source feed after fixing the mapping",
                     ["Fix the field mapping of the import", "Reprocess the source feed", "Reconcile totals"],
                     ["Import mapping pointed to the wrong column. Fixed mapping and reprocessed the feed; totals reconcile.",
                      "Corrected the import configuration and reran the feed for the affected period."],
                     {"Data": 2, "Other": 1}, reassign_bias="any"),
        ],
    ),
    Scenario(
        id="APP-USER-ERROR",
        name="User or operator error / missing instruction",
        ci_groups=APP_GROUPS + ["sap", "citrix_vdi"],
        closure_codes={"User error": 3.0, "Operator error": 2.0, "User manual not used": 2.0},
        component="Application", services=APP_SERVICES,
        dependency="user procedure",
        root_cause="the function was used incorrectly (user or operator error)",
        failure_type="no technical fault",
        triggers=[""],
        titles=["Cannot find function in {service}", "Question about {service}", "{service} not doing what I expect"],
        views={
            "user": [
                "I cannot find where to approve the request in the {service}; the button seems to be missing.",
                "When I export from the {service} the file is empty.",
                "The {service} gives an error when I enter the amount.",
            ],
            "engineer": [
                "No errors in the logs on {ci}; the reported behaviour matches incorrect use of the function in the {service}.",
            ],
        },
        strategies=[
            Strategy("user_instruction", "Explain the correct procedure to the user",
                     ["Walk the user through the correct procedure", "Point to the work instruction", "Confirm the user can complete the task"],
                     ["User was filtering on the wrong period, so the export was empty. Explained the filter and pointed to the work instruction; user confirmed it works.",
                      "The approve button is only visible in the 'my tasks' view. Explained this to the user by phone; resolved."],
                     {"User error": 2, "User manual not used": 3}, reassign_bias="low"),
            Strategy("reset_user_settings", "Reset the user's personal settings / profile",
                     ["Back up the user's personal settings", "Reset the application profile", "Let the user retest"],
                     ["User had changed the screen layout so fields were hidden. Reset personal settings; everything visible again.",
                      "Reset the user's application preferences; the error no longer appears."],
                     {"User error": 1.5, "Operator error": 1}, reassign_bias="any"),
            Strategy("fix_operator_procedure", "Correct the operator procedure and rerun the task",
                     ["Identify the missed operator step", "Rerun the task with the correct parameters", "Update the operator runbook"],
                     ["Operator started the job with the wrong run date. Reran with the correct parameters and updated the runbook.",
                      "Operator step skipped during the handover. Performed the step and updated the checklist."],
                     {"Operator error": 3}, reassign_bias="any"),
        ],
    ),
    Scenario(
        id="APP-WORKS-AS-DESIGNED",
        name="Reported behaviour is working as designed",
        ci_groups=APP_GROUPS + ["sap"],
        closure_codes={"No error - works as designed": 1.0},
        component="Application", services=APP_SERVICES,
        dependency="functional design",
        root_cause="no fault: the behaviour matches the functional design",
        failure_type="no technical fault",
        triggers=[""],
        titles=["Unexpected behaviour in {service}", "{service} rounds amounts", "Field locked in {service}"],
        views={
            "user": [
                "The {service} does not allow me to change the date field after submitting; this seems to be a bug.",
                "Amounts in the {service} overview are rounded differently than in the detail screen.",
            ],
            "engineer": [
                "Checked the functional design for the {service}: the field is locked after submission by design.",
            ],
        },
        strategies=[
            Strategy("explain_design", "Explain the designed behaviour to the requester",
                     ["Check the functional design", "Explain the behaviour to the user", "Close as works as designed"],
                     ["Checked with the functional owner: locking after submission is intended. Explained to the user.",
                      "Rounding difference is by design (overview shows rounded totals). Informed the user."],
                     {"No error - works as designed": 3}, reassign_bias="low"),
            Strategy("change_request", "Register a change request for the desired behaviour",
                     ["Confirm the behaviour is by design", "Register the user's wish as a change request", "Inform the user"],
                     ["Behaviour is according to design. Registered the user's wish as change request for the next release.",
                      "Not a fault. Forwarded the request to the product owner as an enhancement."],
                     {"No error - works as designed": 1.5}, reassign_bias="high"),
        ],
    ),
    # ------------------------------------------------------------------ SAP / Citrix / collaboration
    Scenario(
        id="SAP-SHORT-DUMP",
        name="SAP transaction short dump after transport",
        ci_groups=["sap"], closure_codes={"Software": 3.0, "Other": 1.5, "Unknown": 1.0},
        component="SAP application server", services=["SAP Finance", "SAP HR", "SAP procurement"],
        dependency="SAP transport / kernel",
        root_cause="an inconsistent transport caused an ABAP runtime error (short dump) in the transaction",
        failure_type="hard failure",
        triggers=["after the transport of last night", "after the SAP support package import", ""],
        titles=["Short dump in {service}", "SAP transaction terminates", "{service}: runtime error"],
        views={
            "user": [
                "When I start the transaction in {service} I get a runtime error screen and the transaction stops.",
                "Posting in {service} ends with a dump since this morning.",
            ],
            "engineer": [
                "ST22 on {ci} shows ABAP runtime error CALL_FUNCTION_NOT_FOUND after last night's transport.",
                "Short dumps SYNTAX_ERROR in {service} on {ci}; the transported program references an object that was not imported.",
            ],
        },
        strategies=[
            Strategy("import_missing_transport", "Import the missing / corrected transport",
                     ["Analyse the dump in ST22", "Identify the missing object/transport", "Import the corrected transport and retest"],
                     ["Dump caused by a missing function module in the transport sequence. Imported the dependent transport on {ci}; transaction works.",
                      "Transport imported out of order. Re-imported in the correct sequence; no more dumps."],
                     {"Software": 3}, reassign_bias="high"),
            Strategy("implement_sap_note", "Implement the SAP note that corrects the error",
                     ["Search SAP notes for the runtime error", "Implement the note in development and transport", "Verify in production"],
                     ["Implemented the SAP note for the runtime error after the support package; transported to production and verified.",
                      "Known SAP issue; applied the correction note. Dump resolved."],
                     {"Software": 2}, reassign_bias="high"),
            Strategy("reset_buffers", "Reset program buffers / user buffer",
                     ["Reset the program buffer", "Ask the user to log off and on", "Retest the transaction"],
                     ["Buffers were inconsistent after the import. Reset the program buffer on {ci}; transaction runs.",
                      "User buffer reset and re-login solved the dump."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
        ],
        change_affinity=3.0,
    ),
    Scenario(
        id="CITRIX-SESSION", env_applicable=False,
        name="Citrix / VDI session hangs or fails to launch",
        ci_groups=["citrix_vdi"], closure_codes={"Software": 2.0, "Other": 2.0, "Unknown": 1.0, "Hardware": 0.5},
        component="Citrix / VDI farm", services=["published desktop", "published CRM application", "virtual workplace"],
        dependency="user profile store / worker servers",
        root_cause="corrupted roaming user profile or an overloaded worker server",
        failure_type="intermittent failure",
        triggers=["", "after the user's profile grew too large"],
        titles=["Citrix session frozen", "Cannot start {service}", "Virtual desktop hangs at logon"],
        views={
            "user": [
                "My {service} hangs on the welcome screen and never finishes logging on.",
                "The {service} freezes after a few minutes and I have to close the session.",
            ],
            "monitoring": [
                "Load index of worker {ci} at 10000; new sessions are rejected.",
            ],
            "engineer": [
                "Profile load time for the user on {ci} exceeds 5 minutes; the roaming profile is 4 GB and partly corrupt.",
            ],
        },
        strategies=[
            Strategy("reset_profile", "Reset the user's roaming profile",
                     ["Back up the user's profile data", "Reset the roaming profile", "Let the user log on again"],
                     ["User profile was corrupted and 4 GB large. Backed up favorites and documents, reset the profile; logon takes 30 seconds now.",
                      "Reset the Citrix profile of the user after backup. Session starts normally."],
                     {"Software": 2, "Other": 1.5}, reassign_bias="any"),
            Strategy("drain_worker", "Put the overloaded worker in maintenance and reboot it",
                     ["Enable maintenance mode on the worker", "Wait for sessions to drain", "Reboot the worker and re-enable it"],
                     ["Worker {ci} was overloaded by a hung process. Drained it via maintenance mode and rebooted; load balanced again.",
                      "Rebooted worker {ci} after draining sessions; new sessions accepted."],
                     {"Other": 2, "Unknown": 1.5, "Hardware": 1}, reassign_bias="low"),
            Strategy("logoff_session", "Log off the stuck session from the console",
                     ["Find the user's stuck session", "Log it off from the Citrix console", "Ask the user to reconnect"],
                     ["Stuck session found on {ci}; logged it off from Studio and the user could reconnect.",
                      "Session hung in disconnected state. Forced logoff; resolved."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
        ],
    ),
    Scenario(
        id="MAIL-MAILBOX", env_applicable=False,
        name="Mailbox / Outlook connectivity and quota problems",
        ci_groups=["collab"], closure_codes={"Software": 2.0, "Other": 2.0, "Unknown": 1.0},
        component="Exchange / Outlook", services=["e-mail", "shared mailbox", "calendar"],
        dependency="Exchange mailbox database",
        root_cause="mailbox quota exceeded or corrupted local Outlook cache",
        failure_type="hard failure",
        triggers=["", "after the mailbox reached its quota"],
        titles=["Cannot send e-mail", "Outlook disconnected", "Shared mailbox not updating"],
        views={
            "user": [
                "I cannot send e-mails anymore, they stay in my outbox.",
                "Outlook keeps saying 'disconnected' and new mail does not arrive.",
            ],
            "engineer": [
                "Mailbox on {ci} is over its prohibit-send quota; the OST file of the user is also 48 GB.",
            ],
        },
        strategies=[
            Strategy("increase_quota_archive", "Archive old mail / increase the mailbox quota",
                     ["Check the mailbox size against quota", "Enable online archive or increase quota", "Verify mail can be sent"],
                     ["Mailbox exceeded quota. Enabled the online archive and moved mail older than 2 years; sending works.",
                      "Increased quota after approval and asked the user to clean up; resolved."],
                     {"Other": 2, "Software": 1}, reassign_bias="low"),
            Strategy("rebuild_ost", "Rebuild the Outlook profile / OST cache",
                     ["Close Outlook", "Rename the OST file and create a new profile", "Let Outlook resync"],
                     ["Local OST was corrupt. Created a new Outlook profile; mailbox resynced and Outlook stays connected.",
                      "Rebuilt the Outlook cache; connection stable."],
                     {"Software": 2, "Unknown": 1}, reassign_bias="any"),
        ],
    ),
    # ------------------------------------------------------------------ end-user hardware / devices
    Scenario(
        id="EUC-LAPTOP-DISK", ci_subcats=["Laptop", "Desktop"], device_scope=True, env_applicable=False,
        name="Laptop does not boot / disk failure",
        ci_groups=["enduser_hw"], closure_codes={"Hardware": 3.0, "Other": 1.5, "Unknown": 1.0},
        component="Laptop", services=["employee workplace"],
        dependency="local disk / BitLocker",
        root_cause="failing local disk or a BitLocker recovery prompt after a firmware change",
        failure_type="hard failure",
        triggers=["", "after a BIOS update"],
        titles=["Laptop does not start", "Blue screen at boot", "BitLocker recovery screen"],
        views={
            "user": [
                "My laptop does not start anymore, it shows a black screen with a blinking cursor.",
                "At startup my laptop asks for a BitLocker recovery key.",
            ],
            "engineer": [
                "Diagnostics on {ci} report SMART failure on the SSD; the OS cannot be loaded.",
            ],
        },
        strategies=[
            Strategy("replace_disk_reimage", "Replace the disk and reimage the laptop",
                     ["Confirm the disk failure with diagnostics", "Replace the disk", "Reimage the laptop and restore user data from backup"],
                     ["SSD in {ci} failed diagnostics. Replaced the disk, reimaged the laptop and restored the user's data from the network backup.",
                      "Disk defect. Swapped disk and installed the standard image."],
                     {"Hardware": 3}, reassign_bias="any", destructive=True),
            Strategy("bitlocker_recovery", "Provide the BitLocker recovery key and suspend protection for the update",
                     ["Verify the user's identity", "Provide the recovery key", "Suspend BitLocker before future firmware updates"],
                     ["BitLocker prompted after a BIOS update. Provided recovery key after identity check; laptop boots.",
                      "Gave the user the recovery key from AD; resolved."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
            Strategy("hardware_swap", "Swap the laptop for a loan device",
                     ["Give the user a loan laptop", "Send the defective laptop to the supplier", "Transfer the user's data"],
                     ["Provided a loan laptop and sent {ci} to the supplier for repair.",
                      "Laptop swapped; user can work again."],
                     {"Hardware": 2}, reassign_bias="high"),
        ],
    ),
    Scenario(
        id="EUC-PRINTER", ci_subcats=["Printer", "Scanner"], device_scope=True, env_applicable=False,
        name="Printer queue stuck / print jobs not printing",
        ci_groups=["enduser_hw"], closure_codes={"Hardware": 1.5, "Software": 1.5, "Other": 2.0, "Unknown": 1.0},
        component="Printer / print server", services=["branch printing"],
        dependency="print spooler",
        root_cause="stuck print spooler queue or an incompatible printer driver",
        failure_type="hard failure",
        triggers=["", "after a driver update"],
        titles=["Printer not printing", "Print jobs stuck in queue", "Cannot print from workstation"],
        views={
            "user": [
                "Nothing comes out of the printer; my documents stay in the queue.",
                "Printing gives an error and the printer shows offline.",
            ],
            "engineer": [
                "Spooler on the print server hangs on a corrupted job for {ci}; the queue is blocked.",
            ],
        },
        strategies=[
            Strategy("clear_spooler", "Clear the print queue and restart the spooler",
                     ["Delete the stuck job", "Restart the print spooler service", "Print a test page"],
                     ["Corrupted job blocked the queue for {ci}. Removed it and restarted the spooler; test page OK.",
                      "Cleared queue and restarted spooler; printing again."],
                     {"Other": 2, "Unknown": 2, "Software": 1}, reassign_bias="low"),
            Strategy("reinstall_driver", "Reinstall the correct printer driver",
                     ["Remove the current driver", "Install the certified driver version", "Print a test page"],
                     ["New driver caused errors. Reinstalled the certified driver version; printing works.",
                      "Driver replaced with the approved version."],
                     {"Software": 3}, reassign_bias="any"),
            Strategy("printer_hardware_repair", "Repair / replace printer hardware",
                     ["Check the printer's error panel", "Call the supplier engineer", "Replace the defective part"],
                     ["Fuser unit defect on {ci}. Supplier replaced it; printer back in service.",
                      "Printer hardware fault; replaced by supplier."],
                     {"Hardware": 3}, reassign_bias="high"),
        ],
    ),
    Scenario(
        id="BANK-DEVICE", device_scope=True, env_applicable=False,
        name="Branch banking device failure (card reader / cash device)",
        ci_groups=["banking_device"], closure_codes={"Hardware": 3.0, "Software": 1.0, "Other": 2.0, "Unknown": 1.0},
        component="Banking device", services=["branch cash services", "self-service terminal"],
        dependency="card reader / device firmware",
        root_cause="card reader hardware fault or device firmware hang",
        failure_type="hard failure",
        triggers=["", "after the device firmware update"],
        titles=["Self-service terminal out of order", "Card reader not reading cards", "Cash device error"],
        views={
            "user": [
                "The self-service terminal in the branch does not accept any cards.",
                "Customers get an error at the cash device and it goes out of service.",
            ],
            "monitoring": [
                "Device monitoring: {ci} reports status 'card reader fault' and went out of service.",
            ],
        },
        strategies=[
            Strategy("device_reset", "Reset / power-cycle the device",
                     ["Put the device in maintenance", "Power-cycle the device", "Test a transaction"],
                     ["Device {ci} hung. Power-cycled it via remote management; test transaction OK.",
                      "Reset the terminal; back in service."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
            Strategy("replace_card_reader", "Replace the card reader module",
                     ["Dispatch the field engineer", "Replace the card reader", "Run the device self-test"],
                     ["Card reader of {ci} defect. Field engineer replaced the module; self-test passed.",
                      "Replaced card reader; terminal operational."],
                     {"Hardware": 3}, reassign_bias="high"),
            Strategy("firmware_rollback", "Roll back / reinstall the device firmware",
                     ["Check the firmware version", "Reinstall the approved firmware", "Test transactions"],
                     ["Firmware update left {ci} in a boot loop. Reinstalled the approved firmware; device OK.",
                      "Firmware reinstalled; device stable."],
                     {"Software": 3}, reassign_bias="any"),
        ],
    ),
    # ------------------------------------------------------------------ storage
    Scenario(
        id="STOR-CAPACITY",
        name="Storage volume / LUN full causing write failures",
        ci_groups=["storage", "server"], closure_codes={"Hardware": 1.0, "Software": 1.0, "Other": 2.0, "Unknown": 1.0, "Data": 1.0},
        component="Storage volume", services=["file shares", "application data volume", "backup staging area"],
        dependency="SAN LUN / file system",
        root_cause="the storage volume ran out of free capacity",
        failure_type="resource exhaustion",
        triggers=["", "after unexpected growth of log files", "after a large data load"],
        titles=["Disk full on {ci}", "Cannot save files to share", "Write errors on application volume"],
        views={
            "user": [
                "I cannot save anything on the shared drive, it says there is not enough space.",
                "Uploads to the {service} fail since this morning.",
            ],
            "monitoring": [
                "Capacity alert: volume on {ci} at 99% used, threshold 90%.",
                "Storage threshold exceeded on {ci}; free space below 1%.",
            ],
            "engineer": [
                "File system on {ci} is 100% full; the application log directory grew 300 GB in two days.",
            ],
        },
        strategies=[
            Strategy("extend_volume", "Extend the volume / LUN",
                     ["Check the growth trend", "Extend the LUN and file system", "Verify free space and application writes"],
                     ["Volume on {ci} was at 99%. Extended the LUN by 500 GB and grew the file system; writes succeed.",
                      "Added capacity to the volume after approval; alert cleared."],
                     {"Hardware": 2, "Other": 1.5}, reassign_bias="any"),
            Strategy("cleanup_archive", "Clean up / archive old data",
                     ["Identify the largest directories", "Archive or delete old files per retention policy", "Verify free space"],
                     ["Old log files filled the volume. Archived logs older than 30 days per retention policy; 60% free.",
                      "Moved old media/export files to the archive tier; space recovered."],
                     {"Other": 2, "Unknown": 2, "Data": 2}, reassign_bias="low", destructive=True),
            Strategy("fix_log_rotation", "Fix the runaway log growth / rotation",
                     ["Find the process writing excessive logs", "Fix log level / rotation", "Monitor growth"],
                     ["Debug logging had been left on for the application on {ci}. Set log level back to INFO and enabled rotation; growth stopped.",
                      "Log rotation job was broken. Repaired it; disk usage stable."],
                     {"Software": 3}, reassign_bias="high"),
        ],
    ),
    Scenario(
        id="STOR-SAN-PATH",
        name="SAN path failure causing I/O latency",
        ci_groups=["storage", "server"], closure_codes={"Hardware": 3.0, "Other": 1.5, "Unknown": 1.0},
        component="SAN fabric", services=["application data volume", "database storage"],
        dependency="HBA / fibre-channel switch",
        root_cause="a failed SAN path (HBA, SFP or cable) forcing all I/O over the remaining path",
        failure_type="performance degradation",
        triggers=["", "after maintenance in the data center"],
        titles=["High I/O latency on {ci}", "Storage path down on {ci}", "Slow disk performance"],
        views={
            "monitoring": [
                "Multipath alert on {ci}: 2 of 4 paths down, I/O latency 180 ms.",
            ],
            "engineer": [
                "Fibre-channel port errors on the switch port of {ci}; multipathing reports degraded paths and high latency.",
            ],
            "user": [
                "Everything that uses the data on {ci} is extremely slow today.",
            ],
        },
        strategies=[
            Strategy("replace_sfp_cable", "Replace the faulty SFP / fibre cable",
                     ["Identify the port with CRC errors", "Replace the SFP or cable", "Verify all paths are active"],
                     ["CRC errors on the switch port for {ci}. Replaced the SFP; all 4 paths active and latency back to 3 ms.",
                      "Faulty fibre cable replaced; multipath restored."],
                     {"Hardware": 3}, reassign_bias="any"),
            Strategy("replace_hba", "Replace the host bus adapter",
                     ["Check HBA logs", "Replace the HBA in a maintenance window", "Rescan and verify paths"],
                     ["HBA in {ci} failed. Replaced it in a maintenance window; paths restored.",
                      "Host bus adapter swapped by the supplier."],
                     {"Hardware": 2}, reassign_bias="high"),
            Strategy("rescan_paths", "Rescan / reset the multipath configuration",
                     ["Rescan the storage paths", "Reset failed paths in multipath", "Monitor latency"],
                     ["Paths were marked failed after DC maintenance. Rescanned and reset multipath on {ci}; all paths active.",
                      "Multipath reset; latency normal."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
        ],
    ),
    # ------------------------------------------------------------------ database
    Scenario(
        id="DB-SLOW-QUERY",
        name="Slow database queries and timeouts at peak (missing index / stale statistics)",
        ci_groups=["database", "app_server", "app_web"], closure_codes={"Software": 2.0, "Other": 2.0, "Unknown": 1.0, "Data": 0.5},
        component="Database", services=APP_SERVICES,
        dependency="Oracle / SQL Server database",
        root_cause="inefficient query plan caused by a missing index or stale optimizer statistics",
        failure_type="performance degradation",
        triggers=["during peak usage", "after a large data load", ""],
        titles=["Database timeouts for {service}", "Queries very slow on {ci}", "Reports time out"],
        views={
            "user": [
                "Searching for customers in the {service} takes more than a minute and often times out.",
                "Reports in the {service} time out during the busy morning hours.",
            ],
            "monitoring": [
                "Database alert on {ci}: average query time above 30 seconds, sessions waiting on I/O.",
            ],
            "engineer": [
                "AWR report on {ci} shows a full table scan on the transactions table for the search query; the execution plan changed after the data load.",
                "Top SQL on {ci} is the {service} search query doing a full scan; optimizer statistics are 3 weeks old.",
            ],
        },
        strategies=[
            Strategy("add_index", "Add the missing index and verify the execution plan",
                     ["Identify the slow SQL", "Create the missing index in a maintenance window", "Verify the new execution plan"],
                     ["Search query on {ci} did a full table scan. Created an index on customer_name; query time from 45s to 0.3s.",
                      "Added missing composite index after DBA review; timeouts resolved."],
                     {"Software": 2, "Other": 1}, reassign_bias="high"),
            Strategy("gather_statistics", "Refresh optimizer statistics",
                     ["Check statistics age", "Gather fresh statistics on the affected tables", "Verify query timings"],
                     ["Statistics were stale after the bulk load. Gathered stats on the affected tables on {ci}; plan corrected and queries fast again.",
                      "Refreshed optimizer statistics; response times normal."],
                     {"Other": 2, "Unknown": 2, "Data": 1}, reassign_bias="low"),
            Strategy("kill_blocking_session", "Terminate the blocking session after confirmation",
                     ["Identify the blocking session", "Get confirmation from the session owner", "Terminate the blocking session"],
                     ["A long-running ad-hoc query held locks on {ci}. After confirming with the owner, killed the blocking session; waiting sessions completed.",
                      "Blocking session terminated with approval; database responsive."],
                     {"Other": 1.5, "Unknown": 1}, reassign_bias="low", destructive=True),
        ],
    ),
    Scenario(
        id="DB-TABLESPACE-FULL",
        name="Tablespace or transaction log full",
        ci_groups=["database"], closure_codes={"Software": 1.5, "Other": 2.0, "Unknown": 1.0, "Data": 1.0, "Hardware": 0.5},
        component="Database", services=APP_SERVICES,
        dependency="tablespace / transaction log",
        root_cause="the tablespace or transaction log reached its maximum size",
        failure_type="resource exhaustion",
        triggers=["", "after the log backup job failed"],
        titles=["Database error: unable to extend", "Transaction log full on {ci}", "Inserts failing on {ci}"],
        views={
            "monitoring": [
                "Database alert on {ci}: ORA-01653 unable to extend table in tablespace USERS.",
                "Transaction log of the database on {ci} is 100% full.",
            ],
            "user": [
                "We cannot save new records in the {service}; the application says a database error occurred.",
            ],
        },
        strategies=[
            Strategy("extend_tablespace", "Add a datafile / extend the tablespace",
                     ["Check tablespace usage", "Add a datafile or enable autoextend", "Verify inserts succeed"],
                     ["Tablespace on {ci} full. Added a 20 GB datafile; inserts succeed.",
                      "Extended the tablespace; application saving again."],
                     {"Other": 2, "Software": 1, "Hardware": 1}, reassign_bias="any"),
            Strategy("fix_log_backup", "Fix the failing log backup so the log can truncate",
                     ["Check the log backup job", "Fix and run the log backup", "Verify log usage drops"],
                     ["Log backup job failed for 3 days so the transaction log could not truncate. Fixed the job credentials and ran the backup; log usage 5%.",
                      "Repaired the log backup; log space released."],
                     {"Software": 2, "Unknown": 1.5}, reassign_bias="high"),
        ],
    ),
    # ------------------------------------------------------------------ servers / infrastructure
    Scenario(
        id="SRV-CPU-RUNAWAY",
        name="Runaway process causing high CPU on a server",
        ci_groups=["server", "app_server"], closure_codes={"Software": 2.0, "Other": 2.0, "Unknown": 1.0},
        component="Server", services=APP_SERVICES,
        dependency="OS scheduler / monitoring agent",
        root_cause="a runaway process (looping service or agent) consuming all CPU",
        failure_type="resource exhaustion",
        triggers=["", "after the monitoring agent update", "after the scheduled scan started"],
        titles=["High CPU on {ci}", "Server {ci} very slow", "CPU at 100% on {ci}"],
        views={
            "monitoring": [
                "CPU utilisation on {ci} at 100% for 45 minutes.",
                "Performance alert: processor queue length high on {ci}.",
            ],
            "user": [
                "The {service} running on {ci} reacts very slowly since this morning.",
            ],
            "engineer": [
                "One process on {ci} is using 98% CPU in a tight loop; other services are starved.",
            ],
        },
        strategies=[
            Strategy("restart_process", "Restart the runaway process / service",
                     ["Identify the process consuming CPU", "Restart the service gracefully", "Verify CPU returns to baseline"],
                     ["Monitoring agent on {ci} looped at 98% CPU. Restarted the agent service; CPU back to 15%.",
                      "Restarted the hanging service on {ci}; CPU normal."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
            Strategy("patch_process", "Update / patch the faulty software",
                     ["Confirm the known bug with the vendor", "Install the fixed version", "Monitor CPU for 24 hours"],
                     ["Known bug in agent version 7.1 causing CPU loop. Upgraded to 7.2 on {ci}; stable for 24h.",
                      "Installed the vendor fix for the looping service."],
                     {"Software": 3}, reassign_bias="high"),
            Strategy("reschedule_task", "Reschedule the heavy scheduled task outside business hours",
                     ["Identify the scheduled task", "Move it outside business hours", "Verify CPU during business hours"],
                     ["Full antivirus scan started at 10:00 on {ci}. Rescheduled to 02:00; no more CPU alerts during the day.",
                      "Moved the heavy job to the night."],
                     {"Software": 1, "Other": 1.5}, reassign_bias="any"),
        ],
    ),
    Scenario(
        id="SRV-PATCH-REBOOT",
        name="Server or service not available after patching / reboot",
        ci_groups=["server", "app_server"], closure_codes={"Software": 2.5, "Other": 2.0, "Unknown": 1.0, "Hardware": 0.5},
        component="Server", services=APP_SERVICES,
        dependency="patch management / service start-up order",
        root_cause="services did not start after the patch reboot (start-up dependency or failed patch)",
        failure_type="hard failure",
        triggers=["after the monthly patch weekend", "after the reboot last night"],
        titles=["{service} down after patching", "Server {ci} not reachable after reboot", "Service not started on {ci}"],
        views={
            "user": [
                "Since Monday morning the {service} is not available.",
            ],
            "monitoring": [
                "Service check on {ci}: application service stopped since the maintenance window.",
            ],
            "engineer": [
                "After the patch reboot the application service on {ci} did not start because the database service it depends on was not yet available.",
                "Patch installation on {ci} failed halfway; the server hangs at 'configuring updates'.",
            ],
        },
        strategies=[
            Strategy("start_services", "Start the services manually and fix the start-up order",
                     ["Check which services are stopped", "Start the services in the correct order", "Set a delayed start / dependency"],
                     ["Application service on {ci} started before its database. Started it manually and configured a delayed start.",
                      "Services started by hand after the reboot; dependency added."],
                     {"Other": 2, "Unknown": 2, "Software": 1}, reassign_bias="low"),
            Strategy("rollback_patch", "Roll back the failed patch",
                     ["Boot into recovery / previous state", "Uninstall the failed patch", "Reschedule patching after analysis"],
                     ["Patch KB update hung on {ci}. Rolled back via snapshot and excluded the patch until the vendor fix.",
                      "Uninstalled the failing patch; server operational."],
                     {"Software": 3}, reassign_bias="high"),
        ],
        change_affinity=3.0,
    ),
    # ------------------------------------------------------------------ network
    Scenario(
        id="NET-VPN",
        name="VPN tunnel drops / remote users disconnected",
        ci_groups=["network", "security_sw"], closure_codes={"Hardware": 1.0, "Software": 2.0, "Other": 2.0, "Unknown": 1.0},
        component="VPN gateway", services=["remote access VPN", "site-to-site VPN"],
        dependency="VPN concentrator / IKE negotiation",
        root_cause="VPN tunnel renegotiation failure (IKE/SA mismatch or MTU problems)",
        failure_type="intermittent failure",
        triggers=["", "after the firewall change", "after the VPN client update"],
        titles=["VPN keeps disconnecting", "Site-to-site tunnel down", "Remote users cannot connect"],
        views={
            "user": [
                "My VPN connection drops every 10 minutes when working from home.",
                "Remote colleagues cannot connect to the office network since this morning.",
            ],
            "monitoring": [
                "Tunnel monitor: site-to-site VPN on {ci} flapping, 14 down events in the last hour.",
            ],
            "engineer": [
                "IKE phase 2 renegotiation fails on {ci}: proposal mismatch after the peer changed its encryption settings.",
            ],
        },
        strategies=[
            Strategy("reset_tunnel", "Reset the tunnel / security associations",
                     ["Clear the security associations", "Re-establish the tunnel", "Monitor stability"],
                     ["Cleared IKE/IPsec SAs on {ci}; tunnel re-established and stable for 4 hours.",
                      "Reset VPN tunnel; users reconnected."],
                     {"Other": 2, "Unknown": 2}, reassign_bias="low"),
            Strategy("align_ike_config", "Align IKE / IPsec proposals with the peer",
                     ["Compare the proposals on both ends", "Correct the mismatched settings via change", "Verify renegotiation"],
                     ["Peer changed to AES-256/SHA-256. Aligned the proposal on {ci}; renegotiations succeed.",
                      "Corrected phase 2 settings; tunnel stable."],
                     {"Software": 2}, reassign_bias="high"),
            Strategy("fix_mtu", "Lower the MTU / enable MSS clamping",
                     ["Test with different packet sizes", "Set MSS clamping on the tunnel", "Verify applications over VPN"],
                     ["Fragmentation over the tunnel dropped sessions. Enabled MSS clamping at 1360 on {ci}; drops stopped.",
                      "Adjusted MTU for the VPN; connection stable."],
                     {"Software": 1, "Hardware": 1}, reassign_bias="any"),
        ],
    ),
    Scenario(
        id="NET-SWITCH-PORT",
        name="Intermittent connectivity due to faulty switch port or duplex mismatch",
        ci_groups=["network"], closure_codes={"Hardware": 3.0, "Other": 1.5, "Unknown": 1.0, "Software": 0.5},
        component="Network switch", services=["branch network", "data center LAN"],
        dependency="switch port / cabling",
        root_cause="faulty switch port or cable (or a speed/duplex mismatch) causing packet loss",
        failure_type="intermittent failure",
        triggers=["", "after the cabling work"],
        titles=["Packet loss on {ci}", "Network drops in the branch", "Intermittent connectivity"],
        views={
            "user": [
                "The network in our branch keeps dropping for a few seconds; applications disconnect.",
            ],
            "monitoring": [
                "Interface errors increasing on {ci}; 5% packet loss to the branch.",
            ],
            "engineer": [
                "Port on {ci} shows late collisions and CRC errors; the device negotiated half duplex.",
            ],
        },
        strategies=[
            Strategy("replace_port_cable", "Move to another port / replace the cable",
                     ["Check interface error counters", "Patch to a spare port or replace the cable", "Verify error counters stay at zero"],
                     ["CRC errors on port 12 of {ci}. Moved the uplink to a spare port and replaced the patch cable; no errors since.",
                      "Replaced the faulty cable; packet loss gone."],
                     {"Hardware": 3}, reassign_bias="any"),
            Strategy("fix_duplex", "Correct the speed/duplex configuration",
                     ["Check negotiated speed/duplex on both ends", "Set matching speed/duplex", "Verify error counters"],
                     ["Duplex mismatch on {ci}. Set both sides to auto-negotiate; collisions stopped.",
                      "Fixed speed/duplex settings; connection stable."],
                     {"Software": 2, "Other": 1}, reassign_bias="low"),
            Strategy("failover_link", "Fail over to the redundant link and replace the switch",
                     ["Fail traffic over to the redundant link", "Replace the defective switch", "Fail back and verify"],
                     ["Switch {ci} had a failing backplane. Traffic moved to the redundant link, switch replaced by supplier.",
                      "Hardware replaced after failover."],
                     {"Hardware": 2}, reassign_bias="high"),
        ],
    ),
    # ------------------------------------------------------------------ security / system software
    Scenario(
        id="SEC-CERT-EXPIRY",
        name="Expired TLS certificate breaking service-to-service connections",
        ci_groups=["security_sw", "app_server", "app_web", "server"], closure_codes={"Software": 2.0, "Other": 2.0, "Unknown": 1.0},
        component="TLS certificate", services=APP_SERVICES,
        dependency="PKI / certificate store",
        root_cause="a TLS certificate expired, so TLS handshakes between services fail",
        failure_type="hard failure",
        triggers=["at midnight when the certificate expired", ""],
        titles=["SSL handshake errors on {ci}", "Certificate expired for {service}", "Secure connection failed"],
        views={
            "user": [
                "The {service} shows 'your connection is not private' since this morning.",
            ],
            "monitoring": [
                "Interface monitor: TLS handshake failures between {ci} and the backend since 00:00.",
            ],
            "engineer": [
                "Logs on {ci} show 'PKIX path validation failed: certificate expired' when calling the backend of the {service}.",
            ],
        },
        strategies=[
            Strategy("renew_certificate", "Renew and install the certificate",
                     ["Confirm the expiry date", "Request and install the renewed certificate", "Restart the listener and test"],
                     ["Server certificate on {ci} expired at midnight. Installed the renewed certificate and restarted the listener; handshake OK.",
                      "Renewed certificate via PKI and deployed it; connections restored."],
                     {"Software": 2, "Other": 2}, reassign_bias="any"),
            Strategy("update_truststore", "Update the trust store with the new CA chain",
                     ["Check the certificate chain", "Import the new intermediate CA into the trust store", "Restart and test"],
                     ["Backend presented a certificate from a new intermediate CA not in the trust store of {ci}. Imported the chain; calls succeed.",
                      "Trust store updated with the new CA; resolved."],
                     {"Software": 2, "Unknown": 1}, reassign_bias="high"),
        ],
    ),
    Scenario(
        id="SEC-ACCOUNT-LOCKOUT",
        name="Account lockouts caused by stale stored credentials",
        ci_groups=["security_sw", "app_server", "app_web", "app_desktop", "server"],
        closure_codes={"Other": 2.0, "Unknown": 1.0, "Software": 1.0, "User error": 1.5},
        component="Authentication service", services=APP_SERVICES,
        dependency="Active Directory",
        root_cause="stale credentials stored on a device or in a scheduled task repeatedly lock the account",
        failure_type="intermittent failure",
        triggers=["after the password change", ""],
        titles=["Account locked repeatedly", "Service account locked out", "User keeps getting locked out"],
        views={
            "user": [
                "My account gets locked every morning even though I type the correct password.",
            ],
            "monitoring": [
                "AD alert: service account for the {service} locked out 6 times in 1 hour.",
            ],
            "engineer": [
                "Lockout source is {ci}: a scheduled task still uses the old password after the password change.",
            ],
        },
        strategies=[
            Strategy("update_stored_credentials", "Find the lockout source and update the stored credentials",
                     ["Trace the lockout source in the domain controller logs", "Update the stale credentials on that source", "Unlock the account"],
                     ["Lockout source was a mapped drive on the old laptop still using the previous password. Removed it and unlocked the account.",
                      "Scheduled task on {ci} used old credentials. Updated the task and unlocked the service account."],
                     {"Other": 2, "Software": 1}, reassign_bias="any"),
            Strategy("reset_password", "Unlock the account and reset the password",
                     ["Verify the user's identity", "Unlock and reset the password", "Ask the user to update the password on mobile devices"],
                     ["Unlocked the account and reset the password after identity check; user updated the password on the phone.",
                      "Account unlocked, new password set."],
                     {"User error": 3, "Unknown": 1.5}, reassign_bias="low"),
        ],
    ),
    Scenario(
        id="SEC-ENDPOINT-BLOCK",
        name="Endpoint security / encryption agent blocking an application",
        ci_groups=["security_sw", "app_desktop"], closure_codes={"Software": 3.0, "Other": 1.5, "Unknown": 1.0},
        component="Endpoint security agent", services=["workstation applications"],
        dependency="endpoint protection policy",
        root_cause="the endpoint protection / encryption agent quarantines or blocks the application's files",
        failure_type="hard failure",
        triggers=["after the security policy update", "after the agent update", ""],
        titles=["Application blocked by security software", "Program will not start", "Files quarantined"],
        views={
            "user": [
                "The application does not start anymore; I see a message from the security software.",
            ],
            "engineer": [
                "Endpoint agent on {ci} quarantined the application's DLL after the policy update (false positive).",
            ],
        },
        strategies=[
            Strategy("add_exclusion", "Add a reviewed exclusion for the false positive",
                     ["Confirm the detection is a false positive", "Add a reviewed exclusion in the policy", "Restore the quarantined file"],
                     ["False positive on the application DLL. Security reviewed and added an exclusion; restored the file and the application starts.",
                      "Exclusion added after review; resolved."],
                     {"Software": 2, "Other": 1}, reassign_bias="high"),
            Strategy("rollback_policy", "Roll back the policy / agent update",
                     ["Identify the policy change", "Roll back to the previous policy", "Verify on affected workstations"],
                     ["New policy blocked the application on many workstations. Rolled back to the previous policy; application works.",
                      "Policy rollback done; verified."],
                     {"Software": 2, "Unknown": 1}, reassign_bias="any"),
        ],
        change_affinity=2.0,
    ),
]

SCENARIO_BY_ID = {s.id: s for s in SCENARIOS}


# ------------------------------------------------------------------ novel probes
# Incidents with no plausible historical match. They are *not* indexed; they are the positive
# class for Novel Incident Detection validation. A few are deliberately "hard" (they share
# surface vocabulary with a known family) so the reported false-known rate is meaningful.
NOVEL_PROBES: list[dict] = [
    {"text": "The GPS time server in the data center lost satellite lock and trading hosts are drifting more than 2 seconds from UTC.", "hard": False},
    {"text": "Badge readers at the main entrance reject every employee pass since the building power maintenance.", "hard": False},
    {"text": "The UPS battery bank in the branch failed its self-test and the site is running without battery backup.", "hard": False},
    {"text": "Robotic tape library arm is jammed and the weekly offsite tape rotation cannot be performed.", "hard": False},
    {"text": "Data center cooling unit CRAC-3 raised a high humidity alarm in server hall B.", "hard": False},
    {"text": "The satellite uplink for the disaster recovery site shows heavy rain fade and link margin below minimum.", "hard": False},
    {"text": "Warehouse barcode scanners pair with the wrong base station and scans are booked on another location.", "hard": False},
    {"text": "The quantum key distribution link between the two data centers desynchronized and key rate dropped to zero.", "hard": False},
    {"text": "Leap second insertion caused the high-frequency trading engine to reject orders with timestamp errors.", "hard": True},
    {"text": "Elevator control system in the office tower sends fault notifications to the IT monitoring mailbox.", "hard": False},
    {"text": "Digital signage screens in all branches display a test pattern after the content provider changed its feed URL.", "hard": False},
    {"text": "Voice logging recorder for the trading floor stopped recording calls on channel group 4.", "hard": False},
    {"text": "The mainframe CICS region abends with ASRA when the new COBOL copybook is used in batch.", "hard": True},
    {"text": "The 3D printer in the innovation lab aborts every print at 60% with a thermal runaway error.", "hard": False},
    {"text": "Hardware security module cluster lost quorum and payment PIN translation requests are queuing.", "hard": True},
    {"text": "Smart building sensors flood the MQTT broker with retained messages and dashboards show stale temperatures.", "hard": False},
    {"text": "Our fax-to-mail gateway converts incoming faxes into blank PDF files.", "hard": False},
    {"text": "The blockchain settlement node fell out of consensus after a chain fork and stopped confirming trades.", "hard": False},
    {"text": "Air quality sensors on the trading floor report CO2 above 2000 ppm and the ventilation system does not react.", "hard": False},
    {"text": "Kubernetes etcd cluster lost quorum after two control-plane nodes were evicted, API server read-only.", "hard": True},
    {"text": "The branch coin-counting machine miscounts 2-euro coins after the calibration visit.", "hard": False},
    {"text": "The conference room video bar echoes remote participants in every meeting since the room was moved.", "hard": False},
    {"text": "Solar inverter monitoring on the office roof stopped reporting generation data to the facility portal.", "hard": False},
    {"text": "Our speech-to-text transcription model for call center QA outputs text in the wrong language.", "hard": False},
    {"text": "The machine learning fraud model scoring service returns identical scores for every transaction after retraining.", "hard": True},
    {"text": "E-ink shelf labels in the staff shop show yesterday's prices because the radio base station is offline.", "hard": False},
    {"text": "The pneumatic tube system between the cash office and the vault is stuck with a carrier inside.", "hard": False},
    {"text": "The sprinkler control panel reports a pressure drop in zone 7 of the archive room.", "hard": False},
    {"text": "The mobile banking app's augmented-reality ATM finder shows ATMs in the sea near the coast.", "hard": False},
    {"text": "A certificate transparency monitor detected a lookalike domain certificate issued for our brand.", "hard": True},
    {"text": "The lobby's customer queue ticket dispenser prints the same ticket number repeatedly.", "hard": False},
    {"text": "The electronic voting system for the shareholder meeting double-counts proxy votes.", "hard": False},
    {"text": "Our text-to-speech IVR reads amounts in cents instead of euros after the voice upgrade.", "hard": False},
    {"text": "Night-vision security cameras in the parking garage record only black frames after sunset.", "hard": False},
    {"text": "Gravity-fed coolant loop for the GPU cluster shows air bubbles and the pumps are cavitating.", "hard": False},
    {"text": "The mailroom franking machine refuses to print postage because its postal licence expired.", "hard": True},
    {"text": "Braille display devices for visually impaired staff disconnect when the screen reader updates.", "hard": False},
    {"text": "The weather radar feed used by the facilities team stopped updating on the building operations screen.", "hard": False},
    {"text": "The helicopter pad lighting controller on the head office roof does not switch on at dusk.", "hard": False},
    {"text": "Paper shredder service reports that the confidential waste container sensors are offline.", "hard": False},
]
