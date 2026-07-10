# CRM Pipeline

## Lead Stages

| Stage | Description |
|-------|-------------|
| `new` | Just collected from 2GIS/CSV |
| `qualified` | Passed initial quality checks |
| `landing_generated` | AI/template landing content created |
| `needs_review` | Landing awaiting operator approval |
| `ready_for_outreach` | Landing approved, ready for outreach |
| `contacted` | First outreach message sent |
| `replied` | Lead replied to outreach |
| `interested` | Expressed interest |
| `proposal_sent` | Proposal/offer sent |
| `won` | Converted to customer |
| `lost` | Did not convert |
| `do_not_contact` | Opted out or blocked |

## Valid Transitions

```
new → qualified, do_not_contact
qualified → landing_generated, do_not_contact
landing_generated → needs_review, do_not_contact
needs_review → ready_for_outreach, qualified, do_not_contact
ready_for_outreach → contacted, do_not_contact
contacted → replied, lost, do_not_contact
replied → interested, lost, do_not_contact
interested → proposal_sent, lost, do_not_contact
proposal_sent → won, lost, do_not_contact
won → (terminal)
lost → (terminal)
do_not_contact → (terminal)
```

## Stage History

Every transition is recorded in `lead_stage_history` with:
- From/to stage
- Reason (optional)
- Changed by (operator name)
- Timestamp

## API

- `POST /leads/{lead_id}/stage` — Transition lead stage
- `GET /leads/{lead_id}` — View stage history
- `POST /leads/{lead_id}/do-not-contact` — Block lead with reason
- `DELETE /leads/{lead_id}/do-not-contact` — Unblock lead
