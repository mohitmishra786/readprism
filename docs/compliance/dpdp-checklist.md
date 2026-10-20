# Digital Personal Data Protection (DPDP) Compliance Checklist

*Template: not legal advice. Have qualified Indian privacy counsel review against published DPDP Rules and amendments.*

This checklist tracks ReadPrism's compliance obligations under the **Digital Personal Data Protection Act, 2023 (DPDP Act)** and the **DPDP Rules** for the hosted service deployment (`DEPLOYMENT_MODE=hosted`). For self-hosted deployments, instance operators act as independent Data Fiduciaries.

Enforceability milestone: Full compliance required by **13 May 2027** (with consent-manager provisions phasing in per DPDP Rules).

---

## Statutory Obligations Checklist

| Statutory Section | Obligation | Operational Requirement in ReadPrism | Covering GitHub Issue(s) | Compliance Status |
|---|---|---|---|---|
| **Section 5(1)** | Itemized notice accompanying consent | Pre-consent notice specifying categories of personal data collected (scroll depth, read duration, ratings, newsletters), purposes, withdrawal mechanism, grievance officer contact, and right to file complaint with Board. | [#181](https://github.com/mohitmishra786/readprism/issues/181) | Implemented (PR #331) |
| **Section 5(2)** | Notice in scheduled languages | Provide notice and consent in English and option to access in any of the 22 languages specified in the Eighth Schedule to the Constitution. | *needs an issue* | Needs an issue |
| **Section 6(1)** | Valid consent standard | Consent must be free, specific, informed, unconditional, and unambiguous with clear affirmative action (no pre-ticked checkboxes). | [#181](https://github.com/mohitmishra786/readprism/issues/181), [#178](https://github.com/mohitmishra786/readprism/issues/178) | Implemented (PR #330, #331) |
| **Section 6(4)** | Right to withdraw consent | Ease of withdrawal comparable to giving consent. Users must be able to revoke analytics consent, pause ingestion, or withdraw from collaborative ranking without loss of core reading function. | [#210](https://github.com/mohitmishra786/readprism/issues/210), [#140](https://github.com/mohitmishra786/readprism/issues/140) | Implemented |
| **Section 6(7)** | Interoperability with Consent Managers | Technical integration with registered Consent Managers as operationalized under DPDP Rules. | *needs an issue* | Needs an issue |
| **Section 8(1)** | Lawful processing and purpose limitation | Personal data processed solely for stated purpose (delivering ranked digests and personal relevance scoring). | [#181](https://github.com/mohitmishra786/readprism/issues/181), [#134](https://github.com/mohitmishra786/readprism/issues/134) | Implemented |
| **Section 8(2)** | Processing through Data Processors under valid contract | Written Data Processing Agreement (DPA) with third-party service providers (Groq, Resend, Paddle, cloud hosts). | [#182](https://github.com/mohitmishra786/readprism/issues/182) | Implemented (PR #332) |
| **Section 8(3)** | Accuracy and completeness of personal data | Ensure personal data used in ranking or profile decisions is accurate. Users can view, edit, boost, or mute topic affinities. | [#179](https://github.com/mohitmishra786/readprism/issues/179) | Implemented |
| **Section 8(5)** | Reasonable security safeguards | Implement appropriate technical and organizational measures to prevent breach: TLS 1.3 encryption, salted bcrypt password hashing, per-tenant database isolation, rate-limiting, and hardened Docker profiles. | [#92](https://github.com/mohitmishra786/readprism/issues/92), [#115](https://github.com/mohitmishra786/readprism/issues/115), [#101](https://github.com/mohitmishra786/readprism/issues/101) | Implemented |
| **Section 8(6)** | Intimation of personal data breach | Mandatory notification of confirmed breach to the Data Protection Board of India *without delay* and to affected users. Detailed incident runbook, log evidence, and communication templates. | [#174](https://github.com/mohitmishra786/readprism/issues/174) | Implemented (PR #333) |
| **Section 8(7)** | Storage limitation and data erasure | Erase personal data upon purpose completion or consent withdrawal. Automatic pruning of raw telemetry after 90 days; immediate cascade deletion on account closure. | [#224](https://github.com/mohitmishra786/readprism/issues/224), [#140](https://github.com/mohitmishra786/readprism/issues/140) | Implemented |
| **Section 8(9)** | Publication of Grievance Redressal Officer | Publish business contact details and email of the Grievance Officer on instance website for user inquiries and takedown/grievance requests. | [#183](https://github.com/mohitmishra786/readprism/issues/183) | Implemented (PR #329) |
| **Section 9(1)** | Verifiable parental consent for children | Verifiable consent of parent/lawful guardian prior to processing personal data of a child (individual under 18 years). | *needs an issue* | Needs an issue |
| **Section 9(2)** | Prohibition on behavioral tracking of children | Absolute bar on behavioral monitoring, tracking, or targeted advertising directed at children. Terms exclude accounts under statutory age (#178). Age gating or verification mechanism. | [#178](https://github.com/mohitmishra786/readprism/issues/178), *needs an issue* | Partially addressed in Terms; technical age gate needs an issue |
| **Section 11(1)** | Right to access information about personal data | Data Principal right to receive summary of personal data being processed, processing activities, and identities of all Data Fiduciaries/Processors with whom data has been shared. | [#200](https://github.com/mohitmishra786/readprism/issues/200), [#182](https://github.com/mohitmishra786/readprism/issues/182) | Implemented |
| **Section 12(1)** | Right to correction and updating | Mechanism for Data Principals to correct inaccurate or misleading personal data and complete incomplete data. | [#179](https://github.com/mohitmishra786/readprism/issues/179), [#181](https://github.com/mohitmishra786/readprism/issues/181) | Implemented |
| **Section 12(3)** | Right to erasure | Irreversible deletion of personal data upon request, cascading through all user-owned tables via `DELETE /api/v1/account`. | [#140](https://github.com/mohitmishra786/readprism/issues/140) | Implemented |
| **Section 13** | Right of grievance redressal | Readily available grievance redressal mechanism with established response SLA before Data Principal approaches the Board. | [#183](https://github.com/mohitmishra786/readprism/issues/183), [#136](https://github.com/mohitmishra786/readprism/issues/136) | In Progress (#136 pending counsel review) |
| **Section 14** | Right to nominate | Mechanism for Data Principal to designate another individual to exercise data rights in the event of death or incapacity. | *needs an issue* | Needs an issue |
| **Section 16** | Cross-border data transfer restrictions | Ensure third-party processors reside in permitted jurisdictions and comply with Central Government transfer regulations. Documented subprocessor locations. | [#182](https://github.com/mohitmishra786/readprism/issues/182) | Implemented (PR #332) |

---

## Significant Data Fiduciary (SDF) Obligations (Section 10)

*Note: ReadPrism does not currently meet the volume or sensitivity threshold for designation as a Significant Data Fiduciary by the Central Government. If designated, the following additional requirements apply:*

- [ ] **Resident Data Protection Officer (DPO):** Appoint a DPO based in India reporting to governing body. (*needs an issue*)
- [ ] **Independent Data Auditor:** Periodic audit of compliance posture. (*needs an issue*)
- [ ] **Data Protection Impact Assessment (DPIA):** Formal DPIA process prior to deploying new algorithmic or AI ranking features. (*needs an issue*)
