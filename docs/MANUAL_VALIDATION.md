# Manual spot validation — Pattern Intelligence

Method: `python scripts/sample_families.py 7 5` draws a reproducible random sample of 7 families and 5
members each; I read every sampled description and resolution note next to its generator label. I also
listed every family with scenario purity below 0.85. The notes below are human judgement, not metrics
(the metrics are in `EVALUATION.md`).

## Families that are coherent

| Family | Verdict | Notes |
|---|---|---|
| F004 · Database · slow response — inefficient query plan / missing index | ✅ coherent | Mixes user wording ("searching for customers takes over a minute"), monitoring alerts and engineer wording ("full table scan … outdated optimizer statistics"). All five share one root cause, so this is a genuine cross-symptom family. It also absorbs the **real Source A** tickets "Queries timing out during peak usage". It holds three fix types (add index / refresh statistics / terminate blocking session). The last is destructive, so the guardrail requires ≥ 2 sources plus human confirmation. |
| F014 · Endpoint security false positive | ✅ pure (91/91) | "My work application won't open; the security software shows an error" versus the engineer view "agent quarantined the DLL after a policy update". Rollback-policy and add-exclusion strategies both appear. Two sampled notes are just "closed" and are correctly flagged low quality. The family **name** leads with "End-user device · does not start / boot" because the name is built from the dominant extracted values; the component extraction is imprecise here, but the membership is right. |
| F017 · Storage full — storage capacity exhausted | ✅ coherent | STOR-CAPACITY incidents plus all 22 real Source A "Disk Space Alert" tickets. Scenario *purity* counts this as impure (0.67), but it is the intended cross-source merge: same root cause, same fix family. |
| F021 · Tablespace / transaction log full | ✅ coherent | The alert wording ("unable to extend tablespace USERS") and the user wording ("can't save new loans") are grouped correctly. One member (IM0025543) has a memory-leak description with a log-backup note. It is a **seeded contradiction** that clustered by its resolution text, which shows why contradictory notes matter. |
| F022 · VPN negotiation / MTU | ✅ pure (40/40) | Reset SAs / fix MTU / align IKE all present and separated in the strategy panel. |
| F025 · Citrix corrupt profile / overloaded worker | ✅ pure (26/26) | The LLM repeated "4 GB corrupt roaming profile" in several descriptions, so wording variety is lower here than elsewhere. |

## Families with problems

| Family | Verdict | Notes |
|---|---|---|
| F018 · SAN path failure | ⚠ mostly right (39/48 SAN) | 7 switch-port incidents joined: both describe physical-link errors and latency. One member is a seeded contradiction (an SSO description with a multipath note). |
| F010 · "software fault (per closure code)" | ❌ catch-all (165 members, purity 0.24) | This family collects incidents whose root cause the rule lexicon could **not** extract from the note, so the closure-code fallback ("software fault") dominates the fingerprint. Patch-reboot, release regression, slow-query and batch incidents end up together. This is the clearest weakness of rule-based extraction. An LLM extractor or learned root-cause classifier would fix it; within this family the Evidence Chain shows the root cause as "software fault (per closure code)" with provenance *derived*, which is honest but uninformative. |

## Takeaways

* Where the root cause is stated in the note, families are coherent and cross-symptom, and they merge
  real Source A tickets with the matching Source B families (DB timeout, high CPU, disk space).
* Scenario purity *under*-states quality for those intended cross-source merges (F004, F011, F017).
  It *over*-states nothing we observed, apart from the F010 catch-all it exposes.
* Seeded contradictions (44) end up inside plausible families because clustering uses the resolution
  text. That is one reason the Quality Manager's contradiction flag lowers their influence weight.
