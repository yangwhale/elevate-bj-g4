# HR Policy Corpus

The approved policy documents that the assistant is permitted to answer from. This corpus is the **only** source of policy facts. Anything the agent states that is not in one of these files is a hallucination by definition (`FR-5.2`, `NFR-3.1`).

## Contents

| File | Doc ID | Covers | Used by |
| :--- | :--- | :--- | :--- |
| `leave-policy.md` | HR-POL-001 | Vacation, sick, bereavement, short-term medical, unpaid leave, cancellation | UC-1.1, UC-1.2, UC-2.2 |
| `expense-and-equipment-policy.md` | HR-POL-002 | Expense rules, standard issue, home office equipment, peripherals, travel | UC-1.1, UC-2.1 |
| `remote-work-policy.md` | HR-POL-003 | Work location categories, eligibility, equipment entitlement, temporary work abroad, security | UC-1.1, UC-2.1 |
| `code-of-conduct.md` | HR-POL-004 | Respect at work, gifts and hospitality, conflicts, information handling, AI use | UC-1.1 |
| `relocation-policy.md` | HR-POL-005 | Allowance table, covered and not covered, relocation steps, associated leave | UC-2.3 |
| `it-support-policy.md` | HR-POL-006 | Ticket categories, priority definitions, lifecycle transitions, duplicates | UC-1.3, UC-2.x |

## Why this corpus exists

Evaluation ground truth has to be traceable to a document. Without a corpus, an evaluation set can only assert policy facts that someone invented, which produces a benchmark that **rewards** the exact behaviour `NFR-3.1` forbids. Every expected answer in `tests/eval/datasets/` cites a file and a section in this directory, and every cited section exists.

## Design constraints observed

1. **Internally consistent.** Numbers that appear in more than one document agree. The monitor entitlement is one per three years in both HR-POL-002 §3.2 and HR-POL-003 §3, and the ticket lifecycle in HR-POL-006 §5.2 matches the state machine in `SDD.md` §5.1.3.
2. **Consistent with the systems of record.** WorkWeek accepts only `Vacation` and `Sick`, so bereavement and short-term medical leave are both recorded as `Sick` rather than as categories that do not exist.
3. **Boundaries are explicit.** Each document states which steps the assistant performs and which require a human. This gives the evaluation set a defensible expected refusal rather than a matter of taste.
4. **Contains deliberate hard cases.** Gift thresholds are per giver per year rather than per gift; the relocation allowance is a reimbursement ceiling rather than a payment; bereavement leave is additional to and not deducted from sick leave. Each of these is a question an agent answers wrongly if it skims.

## Ingestion

Files are ingested into the Vertex AI Search datastore described in `SDD.md` §C.2:

```
gsutil -m cp policies/*.md gs://${PROJECT_ID}-hr-policies/
```

Markdown is ingested as unstructured text. The layout parser preserves the `##` headings, which is what makes section-level citation possible.

## Citation URI scheme

Answers cite the GCS object and the section anchor:

```
gs://${PROJECT_ID}-hr-policies/leave-policy.md#4-bereavement-leave
```

The citation resolver in `SDD.md` §4.3.1 verifies that the object exists and that the anchor matches a heading in it. A citation to a heading that does not exist fails `M-4` and the answer is withheld.

## Changing the corpus

A policy change is a pull request against this directory. The PR must also update any evaluation case in `tests/eval/datasets/` whose expected answer depends on the changed text. CI fails when a cited section no longer exists.
