# Data Processing Addendum (DPA) Template

*Template: needs counsel review. Do not sign or execute without legal review by qualified counsel in your jurisdiction.*

This Data Processing Addendum ("DPA") supplements the Terms of Service between **[Customer / Data Controller Name]** ("Controller") and **[ReadPrism Operator / Service Provider Legal Entity Name]** ("Processor").

---

## 1. Parties

- **Data Controller:** [Company Name / Customer Name], with principal place of business at [Address], represented by [Name, Title]. Contact: [Email].
- **Data Processor:** [ReadPrism Operator Legal Entity], with principal place of business at [Address], represented by [Name, Title]. Contact: [Email / Grievance Officer].

## 2. Subject matter

The subject matter of the data processing under this DPA is the provision of the ReadPrism content aggregation, ranking, and personal reading digest service pursuant to the Terms of Service.

## 3. Processing duration

The duration of the processing corresponds to the term of the Controller's subscription or active account on the Service, plus any retention period required by applicable statutory law or until all personal data is deleted pursuant to Section 8.

## 4. Categories of data

The personal data processed includes:
- **User Account Data:** Name, email address, password hash, account preferences, timezone, display name.
- **Reading Telemetry & Behavioral Signal:** Reading interactions, scroll depth, active reading duration, article ratings, topic boost/mute preferences.
- **Followed Sources & Subscriptions:** RSS/Atom feeds, tracked creator identifiers, and forwarded newsletter messages submitted to the user's private inbox.
- **Derived Ranking Weights:** Learned interest node scores, topic cluster affinities, and source trust ratings.
- **Data Subjects:** Authorized users of the Service designated by Controller.

## 5. Subprocessors

Controller grants general authorization to Processor to engage third-party subprocessors to support delivery of the Service. A current list of subprocessors is maintained at [/subprocessors](https://readprism.app/subprocessors) and in `docs/THIRD_PARTY_SERVICES.md`.

Processor shall:
1. Impose data protection terms on any subprocessor no less protective than those in this DPA;
2. Remain liable to Controller for the performance of the subprocessor's obligations;
3. Provide notice of intended changes concerning the addition or replacement of subprocessors with an opportunity to object.

## 6. Security measures

Processor shall implement and maintain appropriate technical and organizational measures to ensure a level of security appropriate to the risk, including:
- Encryption of data in transit (TLS 1.3/HTTPS) and encryption of sensitive credentials (API keys, passwords with salted bcrypt);
- Per-tenant data isolation enforcing strict user boundary checks on database queries;
- Role-based access controls and least-privilege administrative access;
- Automated regular database backups and vulnerability scanning.

## 7. Breach notice

In the event of a confirmed Personal Data Breach affecting Controller's personal data, Processor shall notify Controller without undue delay (and within the statutory period prescribed by applicable law, e.g. 72 hours under GDPR, or without delay under the DPDP Act) after becoming aware of the breach. The notice shall describe:
1. The nature of the breach, including categories and approximate number of data subjects and records concerned;
2. The name and contact details of the data protection officer or contact point;
3. The likely consequences of the breach;
4. The measures taken or proposed to address the breach and mitigate potential adverse effects.

## 8. Deletion and return of data

Upon termination of the Services or upon Controller's written request, Processor shall, at Controller's choice, delete or return all personal data processed on behalf of Controller, and delete existing copies unless applicable statutory law requires continued storage. Account erasure may also be initiated directly via the Service API (`DELETE /api/v1/account`) or within account preferences.

---

**Signatures (for execution):**

| For Controller: | For Processor: |
|---|---|
| Signature: _________________________ | Signature: _________________________ |
| Name: [Controller Signatory] | Name: [Processor Signatory] |
| Title: [Title] | Title: [Title] |
| Date: [Date] | Date: [Date] |
