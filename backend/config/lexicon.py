"""Rule lexicons shared by query understanding (Phase 3) and the enriched fingerprint (Phase 4).

Each rule is a regex over lower-cased text mapped to a canonical label. Rules are documented and
deterministic, so every extracted value is traceable ("derived" from original text, or tagged
"synthetic" when the text itself was generated).

Caveat: these lexicons were written with IT-operations domain knowledge
that overlaps the synthetic scenario catalog, so extraction accuracy measured on synthetic text
overstates accuracy on arbitrary real free text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern
    label: str
    concepts: tuple[str, ...] = ()
    failure_type: str | None = None
    extra: dict = field(default_factory=dict)


def R(p: str, label: str, concepts: tuple[str, ...] = (), failure_type: str | None = None) -> Rule:
    return Rule(re.compile(p, re.I), label, concepts, failure_type)


# ------------------------------------------------------------------ symptoms (+ vague→technical)
SYMPTOM_RULES: list[Rule] = [
    R(r"\b(slow(?:er|ly|ness)?|sluggish|takes? (?:forever|ages|minutes|very long)|lag(?:gy|s)?\b|crawl\w*|"
      r"response times?|latency|degrad\w*|performance)", "slow response",
      ("performance degradation", "high latency", "slow response time"), "performance degradation"),
    R(r"\b(freez\w*|froze|hangs?\b|hanging|hung\b|unresponsive|not responding|stop(?:s|ped)? responding|"
      r"locks? up|becomes? stuck)", "freeze / hang",
      ("application freeze", "unresponsive", "hang"), "performance degradation"),
    R(r"\b(time[sd]? ?out|timing out|timeouts?)\b", "timeout",
      ("timeout", "request timeout", "connection exhaustion"), "intermittent failure"),
    R(r"((?:can(?:no|')?t|unable to|not able to|nobody can) (?:log ?in|sign ?in|login)|login (?:loop|fail\w*)|"
      r"access denied|authentication fail\w*|\bsso\b|back to the login|saml|kerberos)", "login failure",
      ("authentication failure", "single sign-on", "login"), "hard failure"),
    R(r"(account\w* (?:gets |is |keeps getting )?locked|locked out|lockouts?)", "account lockout",
      ("account lockout", "stale credentials"), "intermittent failure"),
    R(r"(unauthori[sz]ed|brute.force|intrusion|multiple failed login|suspicious login)", "unauthorized access attempt",
      ("unauthorized access", "brute force", "security incident"), "security event"),
    R(r"(error (?:page|message|screen)|generic error|exception|runtime error|short dump|\bdump\b|abend|"
      r"crash\w*|nullpointer)", "application error / crash",
      ("application error", "exception", "crash"), "hard failure"),
    R(r"((?:does ?n.?t|do not|not|won.?t) (?:start|boot)|black screen|blue screen|bitlocker|smart failure)",
      "does not start / boot", ("start-up failure", "boot failure", "disk failure"), "hard failure"),
    R(r"(not enough (?:disk )?space|disk (?:is )?full|no (?:free )?space|out of space|capacity alert|"
      r"storage (?:threshold|exceeded)|\b(?:99|100)% (?:used|full)|quota|threshold exceeded)", "storage full",
      ("storage capacity", "disk full", "free space"), "resource exhaustion"),
    R(r"(\bcpu\b|processor|excessive cpu|tight loop)", "high CPU",
      ("high CPU", "runaway process", "resource exhaustion"), "resource exhaustion"),
    R(r"(\bheap\b|out of memory|memory (?:usage|leak|pressure|climbs)|garbage.collection|\bgc pauses?)",
      "memory pressure", ("memory leak", "heap exhaustion", "garbage collection"), "resource exhaustion"),
    R(r"(yesterday.?s (?:figures|data)|no data|reports? .*empty|empty report|data was not loaded|"
      r"not (?:been )?(?:loaded|updated)|overnight update|job (?:chain )?(?:failed|aborted|ended)|return code|"
      r"interface (?:file|error)|batch job|import job)", "missing or stale data",
      ("batch job failure", "interface file", "data load"), "hard failure"),
    R(r"((?:wrong|incorrect|duplicate|corrupt\w*) (?:data|records?|address\w*|contracts?|details|values?|figures)|"
      r"referential integrity|data.quality)", "incorrect data",
      ("data quality", "data corruption", "import error"), "data integrity"),
    R(r"(\bvpn\b|tunnel|remote access|working from home|remote colleagues)", "VPN disconnects",
      ("VPN", "tunnel renegotiation", "remote access"), "intermittent failure"),
    R(r"(packet loss|network (?:drops|keeps dropping|is down)|keeps dropping|disconnect\w*|connectivity|"
      r"interface errors|crc errors|collisions)", "network connectivity loss",
      ("packet loss", "network connectivity", "link errors"), "intermittent failure"),
    R(r"(\bprint\w*|spool\w*)", "printing fails", ("print queue", "printer", "spooler"), "hard failure"),
    R(r"(certificate|\bssl\b|\btls\b|handshake|not private|pkix)", "certificate / TLS error",
      ("certificate expiry", "TLS handshake", "PKI"), "hard failure"),
    R(r"(cannot send|outbox|outlook|mailbox|e-?mails?\b)", "mail problem",
      ("mailbox", "Outlook", "Exchange"), "hard failure"),
    R(r"(citrix|virtual desktop|published (?:desktop|app\w*)|virtual workplace|session (?:hangs|frozen|will not))",
      "virtual session problem", ("Citrix", "VDI session", "user profile"), "intermittent failure"),
    R(r"(card reader|cash device|cash dispenser|self-service terminal|out of service)", "banking device fault",
      ("card reader", "banking device", "device firmware"), "hard failure"),
    R(r"(security software|quarantin\w*|blocked by|false positive|antivirus|endpoint (?:agent|protection))",
      "blocked by endpoint security", ("endpoint protection", "quarantine", "security policy"), "hard failure"),
    R(r"(stream(?:ing)?\b|broadcast|video)", "stream failure", ("streaming", "media delivery"), "hard failure"),
    R(r"(encod\w*|codec|media conversion)", "encoder failure", ("encoder", "codec", "media conversion"), "hard failure"),
    R(r"(cache miss|\bcdn\b|media loading)", "slow media delivery", ("CDN cache", "cache miss"), "performance degradation"),
    R(r"(i/o latency|paths? (?:are |is )?down|multipath|fibre.channel|storage path)", "storage I/O latency",
      ("SAN path", "I/O latency", "multipath"), "performance degradation"),
    R(r"(unable to extend|tablespace|transaction log (?:is )?(?:\d+% )?full|ora-\d+)", "database space exhausted",
      ("tablespace full", "transaction log full"), "resource exhaustion"),
    R(r"(full (?:table )?scan|execution plan|optimi[sz]er|slow quer\w*|query time|queries (?:are )?(?:slow|timing))",
      "slow queries", ("slow query", "missing index", "execution plan"), "performance degradation"),
    R(r"(not available|unavailable|\bdown\b|outage|not reachable|cannot connect|service stopped)",
      "service unavailable", ("service unavailable", "outage"), "hard failure"),
    R(r"(button does nothing|does ?n.?t work|not working|stopped working|broken|cannot (?:find|finish|save|approve)|"
      r"fails? (?:intermittently|at step))", "function not working", ("functional defect",), "functional failure"),
    R(r"(rounded|rounding|locked after|by design|seems to be a bug|different(?:ly)? than)", "unexpected behaviour",
      ("expected behaviour", "functional design"), "no technical fault"),
]

# ------------------------------------------------------------------ components (text)
COMPONENT_RULES: list[Rule] = [
    R(r"(database|\bsql\b|quer(?:y|ies)|tablespace|oracle|\bdb\b|\bdba\b|ora-\d+|awr)", "Database"),
    R(r"(\bsso\b|authentication|log ?in|adfs|active directory|\bad\b sync|kerberos|saml|identity provider|"
      r"account (?:gets |is )?locked|locked out)", "Authentication service"),
    R(r"(\bvpn\b|tunnel|ipsec|\bike\b)", "VPN gateway"),
    R(r"(\bswitch\b|router|packet loss|network|\bport\b|duplex|crc)", "Network"),
    R(r"(\bsan\b|\blun\b|volume|storage|disk space|file ?system|shared drive|\bhba\b|multipath)", "Storage"),
    R(r"(laptop|desktop pc|workstation|bitlocker|\bbios\b)", "End-user device"),
    R(r"(printer|print (?:queue|job|server)|spooler)", "Printer"),
    R(r"(card reader|cash device|self-service terminal|banking device)", "Banking device"),
    R(r"(citrix|\bvdi\b|virtual desktop|published desktop|worker server|virtual workplace)", "Citrix / VDI"),
    R(r"(outlook|exchange|mailbox|e-?mail)", "Mail (Exchange/Outlook)"),
    R(r"(\bsap\b|abap|st22|transaction code|sap transport)", "SAP"),
    R(r"(certificate|\btls\b|\bssl\b|pkix|trust ?store)", "TLS certificate"),
    R(r"(security software|endpoint|antivirus|quarantin)", "Endpoint security"),
    R(r"(batch|job chain|scheduler|interface file|import job|nightly)", "Batch / interface"),
    R(r"(\bcpu\b|server|reboot|patch)", "Server"),
    R(r"(encoder|codec|stream|\bcdn\b|media|broadcast)", "Media platform"),
    R(r"(application|\bapp\b|portal|system|screen|dashboard)", "Application"),
]

CI_GROUP_COMPONENT = {
    "app_server": "Application", "app_web": "Application", "app_desktop": "Application", "sap": "SAP",
    "citrix_vdi": "Citrix / VDI", "collab": "Mail (Exchange/Outlook)", "enduser_hw": "End-user device",
    "banking_device": "Banking device", "storage": "Storage", "database": "Database", "server": "Server",
    "network": "Network", "security_sw": "Endpoint security", "media": "Media platform",
}

# ------------------------------------------------------------------ root causes (resolution / engineer text)
ROOT_CAUSE_RULES: list[Rule] = [
    R(r"(memory leak|heap (?:was )?(?:almost )?exhaust\w*|heap usage|session cache|heap dump|\bgc\b|jvm)", "memory leak / heap exhaustion"),
    R(r"(connection pool|pool (?:was )?exhausted|connection leak|stuck connections|close its db connection|"
      r"connection close)", "connection pool exhaustion"),
    # "after the new version" alone is a TRIGGER, not a root cause — a defect must be stated
    R(r"(defect .{0,40}(?:release|build|version|deploy)|(?:release|build|version) .{0,25}(?:defect|bug)|regression|"
      r"rolled? .{0,20}back .{0,30}release|release (?:was )?rolled back|hotfix|feature (?:toggle|flag))",
      "release defect (regression)"),
    R(r"((?:token.)?signing certificate|federation|\bidp\b|directory sync|group membership|\bad\b sync|forced ad sync|"
      r"stale sessions|session store)", "SSO / directory sync failure"),
    R(r"(interface file|input file|file (?:not found|arrived late|was delivered)|malformed|invalid date format|"
      r"upstream|redeliver\w*|file-watcher|cut-off)", "missing or malformed interface file"),
    R(r"((?:bulk )?import (?:had )?(?:overwrote|mapping|corrupted)|wrong column|faulty import|correction script|"
      r"data owner|reprocessed the feed)", "faulty data import"),
    R(r"(wrong (?:period|filter|parameters|run date)|incorrect use|user error|operator (?:started|step)|skipped|"
      r"explained (?:the|this)|work instruction|walked the user)", "user / operator error"),
    R(r"(by design|functional design|intended|works as designed|according to design|not a fault)", "works as designed (no fault)"),
    R(r"(transport|short dump|abap|sap note|support package|program buffer|user buffer)", "SAP transport / program error"),
    R(r"(profile (?:was )?corrupt\w*|roaming profile|citrix profile|worker .{0,20}overloaded|load index|"
      r"stuck session|drained)", "corrupt user profile / overloaded worker"),
    R(r"(quota|online archive|\bost\b|outlook profile|outlook cache)", "mailbox quota / corrupt OST"),
    R(r"(\bssd\b|disk (?:failed|defect)|smart failure|disk defect|bitlocker|recovery key|loan laptop)", "hardware failure (disk / device)"),
    R(r"(spooler|corrupted job|printer driver|certified driver|fuser)", "print spooler / driver fault"),
    R(r"(card reader|firmware|power-cycl\w*|terminal hung)", "device hardware / firmware fault"),
    R(r"(volume .{0,30}(?:99|100)%|extended the lun|added capacity|log files? (?:filled|grew)|debug logging|"
      r"log rotation|archived logs|space recovered|storage exceeded|archive old media|expand storage)", "storage capacity exhausted"),
    R(r"(crc errors|\bsfp\b|\bhba\b|host bus adapter|fibre cable|multipath|paths? (?:were )?(?:marked )?(?:down|failed))", "SAN path failure"),
    R(r"(full table scan|missing (?:composite )?index|created an index|add(?:ed)? (?:missing )?index\w*|statistics|"
      r"execution plan|blocking session|held locks|optimi[sz]e query)", "inefficient query plan / missing index"),
    R(r"(tablespace|datafile|transaction log|log backup)", "tablespace / transaction log full"),
    R(r"(loop\w*|runaway|98% cpu|antivirus scan|scan started|agent version|excessive cpu|consuming excessive)", "runaway process"),
    R(r"(patch (?:installation|kb|update)|failing patch|after the (?:patch )?reboot|started before its database|"
      r"delayed start|services? (?:did not start|started by hand)|start-up order)", "failed patch / service start-up order"),
    R(r"(\bike\b|ipsec|proposal|security associations|\bmss\b|\bmtu\b|fragmentation|phase 2)", "VPN negotiation / MTU issue"),
    R(r"(duplex|collisions|port \d+|patch cable|backplane|spare port)", "faulty switch port / duplex mismatch"),
    R(r"(certificate (?:on .{0,20})?expired|expired at midnight|pkix|intermediate ca|trust ?store|renewed certificate)", "expired certificate / trust store"),
    R(r"(lockout source|old password|stale credential|mapped drive|previous password)", "stale stored credentials"),
    R(r"(false positive|quarantin\w*|exclusion|security policy|policy rollback|new policy)", "endpoint security false positive"),
    R(r"(cache miss|\bcdn\b)", "CDN cache miss"),
    R(r"(encoder crashed|codec)", "encoder / codec failure"),
    R(r"(failed login attempts|block ip|brute.force|multi-factor)", "brute-force login attempts"),
    R(r"(stream stopped|network interface|streaming service)", "streaming service / network interface failure"),
]

# ------------------------------------------------------------------ triggers
TRIGGER_RULES: list[Rule] = [
    R(r"(after (?:the |last night.s |the weekend )?(?:release|deployment|update|new version|upgrade)|since the new version|"
      r"new version was (?:deployed|installed)|since the (?:latest )?deployment|weekend release)", "deployment / release"),
    R(r"(after (?:the )?(?:monthly )?(?:patch\w*|reboot|maintenance)|patch weekend|since the maintenance window|"
      r"after .{0,20}maintenance)", "patching / maintenance"),
    R(r"(config(?:uration)? change|after the change|firewall change|policy update|policy change|changed its|"
      r"after the transport|support package)", "configuration change"),
    R(r"(peak|busy|month.end|start of the month|mornings?\b|high usage|under load|traffic increased)", "load / traffic peak"),
    R(r"(password change)", "password change"),
    R(r"(bulk import|large data load|after a data load|after the data load)", "data load"),
    R(r"(certificate rollover|expired at midnight|at midnight)", "certificate expiry"),
    R(r"(firmware update|bios update|driver update|agent update|client update)", "firmware / driver update"),
    R(r"(nightly run|overnight|during the night|cut-off)", "scheduled batch window"),
]

ENVIRONMENT_RULES: list[Rule] = [
    R(r"\b(production|prod|live environment)\b", "Production"),
    R(r"\b(acceptance|staging|uat|test environment|pre-?prod)\b", "Staging"),
    R(r"\b(development|dev environment|\bdev\b)\b", "Development"),
]

SCOPE_RULES: list[Rule] = [
    R(r"(all users|everyone|nobody can|organi[sz]ation|organi[sz]ation.wide|all branches|whole company)", "organization-wide"),
    R(r"(several departments|multiple departments|department)", "department"),
    R(r"(whole team|our team|the team|one team|several devices|more than one device)", "team"),
    R(r"(some colleagues|a few colleagues|several users|multiple users|few users|colleagues|many users|small group)", "multiple users"),
    R(r"(only me|only i\b|single user|just me|one user|only my|i seem to be the only)", "single user"),
]

DEPENDENCY_RULES: list[Rule] = [
    R(r"(oracle|sql server|database|\bdb\b)", "database"),
    R(r"(active directory|adfs|\bidp\b|identity provider|\bad\b sync|directory)", "identity provider / Active Directory"),
    R(r"(upstream|interface file|sending team|supplier (?:redelivered|system))", "upstream system"),
    R(r"(\bsan\b|fibre|\blun\b)", "SAN storage"),
    R(r"(\bcdn\b)", "CDN"),
    R(r"(firewall|\bpeer\b)", "network peer / firewall"),
    R(r"(\bpki\b|\bca\b|certificate authority)", "PKI"),
    R(r"(scheduler|job chain)", "job scheduler"),
    R(r"(connection pool)", "database connection pool"),
    R(r"(profile store|roaming profile)", "user profile store"),
]

SERVICE_PATTERN = re.compile(
    r"\b((?:[a-z][\w-]*\s){0,3}(?:portal|application|system|service|dashboard|app|banking|mailbox|desktop|"
    r"workplace|terminal))\b", re.I)
SERVICE_STOP = {"the", "our", "a", "an", "this", "that", "my", "application", "system", "service", "app"}


def match_all(rules: list[Rule], text: str) -> list[Rule]:
    return [r for r in rules if r.pattern.search(text)]


def first_match(rules: list[Rule], text: str) -> Rule | None:
    for r in rules:
        if r.pattern.search(text):
            return r
    return None


def extract_service(text: str) -> str | None:
    best = None
    for m in SERVICE_PATTERN.finditer(text):
        words = [w for w in m.group(1).lower().split() if w not in SERVICE_STOP]
        if words and (best is None or len(words) > len(best.split())):
            best = " ".join(words + ([m.group(1).split()[-1].lower()] if m.group(1).split()[-1].lower() not in words else []))
    return best
