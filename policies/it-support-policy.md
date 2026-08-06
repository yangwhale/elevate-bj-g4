# IT Support Policy

**Document ID:** HR-POL-006
**Version:** 3.3
**Effective date:** 2026-01-01
**Owner:** IT Service Management
**Applies to:** All employees and contractors raising IT or HR service requests.

---

## 1. Where requests go

All IT and HR service requests are raised as tickets in **ServiceImmediately**. Email and chat requests to individual engineers are not tracked and will be redirected.

---

## 2. Ticket categories

| Category | Use for |
| :--- | :--- |
| `IT` | Connectivity, software faults, access to systems, account problems |
| `Hardware` | Device requests, replacements, faults, peripherals, shipping |
| `HR Access` | Mailbox delegation, calendar routing, leave-related access changes |
| `Facilities` | Building access, badges, desk and room issues |

A ticket in the wrong category is re-categorised by the service desk, which resets the response clock.

---

## 3. Priority definitions

Priority is set from **business impact**, not from urgency as felt by the requester.

| Priority | Definition | Examples |
| :--- | :--- | :--- |
| **1 - Critical** | Complete outage of a production service, or a whole team unable to work, or a confirmed security incident | Company-wide VPN outage; lost or stolen laptop; suspected account compromise |
| **2 - High** | One person entirely unable to work, with no workaround | Laptop will not boot; account locked out with no alternative access |
| **3 - Moderate** | Impaired but able to work, or a time-bound request | Intermittent VPN drops; mailbox delegation before a leave of absence; building access before a start date |
| **4 - Low** | No work impact | New monitor request; software licence request; general question |

### 3.1 Critical requires an impact statement
A ticket may only be raised as `1 - Critical` if the description states an outage, a work stoppage, or a security incident. A ticket marked Critical without such a statement is automatically downgraded to `3 - Moderate` by the service desk, and the requester is notified.

The assistant applies the same rule: it does not raise a Critical ticket unless the employee's description contains an outage, work-stoppage, or security condition.

---

## 4. Response and resolution targets

| Priority | First response | Target resolution |
| :--- | :--- | :--- |
| 1 - Critical | 15 minutes | 4 hours |
| 2 - High | 1 hour | 1 working day |
| 3 - Moderate | 4 working hours | 3 working days |
| 4 - Low | 1 working day | 10 working days |

Targets run during service desk hours, 08:00 to 18:00 local, Monday to Friday, except for `1 - Critical` which runs continuously.

---

## 5. Ticket lifecycle

### 5.1 States
`New` → `In Progress` → `Resolved` → `Closed`

### 5.2 Permitted transitions

| From | To | Allowed |
| :--- | :--- | :---: |
| New | In Progress | Yes |
| New | Resolved | Yes, with resolution notes |
| **New** | **Closed** | **No** |
| In Progress | Resolved | Yes |
| In Progress | Closed | Yes |
| Resolved | In Progress | Yes, reopening within 5 working days |
| Resolved | Closed | Yes |
| Closed | anything | No, a closed ticket is immutable |

A ticket raised in error is moved to `Resolved` with a note, then `Closed`. It is never moved straight from `New` to `Closed`, because that leaves no record of why it was abandoned.

### 5.3 Automatic closure
A `Resolved` ticket closes automatically after **5 working days** without a reopen.

---

## 6. Duplicate tickets

A ticket with the same requester and a substantially identical short description raised within **5 minutes** of an existing one is rejected as a duplicate. The requester is directed to comment on the existing ticket instead.

---

## 7. What the assistant may do

| Action | Permitted |
| :--- | :---: |
| Query the requester's own tickets | Yes |
| Query another person's ticket | **No** |
| Create a ticket for the requester | Yes, after confirmation |
| Comment on the requester's own ticket | Yes, after confirmation |
| Change the status of the requester's own ticket | Yes, after confirmation, within Section 5.2 |
| Change the status of another person's ticket | **No** |
| Change priority after creation | No, this is a service desk action |
| Assign a ticket to an engineer | No |

---

## 8. Security incidents

A suspected security incident is raised as `1 - Critical`, category `IT`, and the requester also notifies the Security team directly. Do not include credentials, tokens, or the contents of a suspicious message in the ticket body; attach them separately when asked.

---

## 9. Related policies

* Remote Work Policy (HR-POL-003), Section 6, for device security requirements
* Expense and Equipment Policy (HR-POL-002), Section 3, for equipment entitlement
