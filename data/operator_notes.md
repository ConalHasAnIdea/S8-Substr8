# Operator Assurance Notes

## Operator Note 1: Transport VendorA Escalation
VendorA transport link_down alarms on customer-facing Ethernet services should use High impact and High urgency because they usually indicate service loss.

## Operator Note 2: Critical Alarm Suppression
Critical alarms are never auto-suppressed. They require visible incident creation unless explicitly cleared by a correlated parent outage ticket.

## Operator Note 3: Alarm Storm Correlation
Alarm storms should correlate by siteId and probableCause before incident creation. Duplicate alarms with the same correlationId should enrich work notes rather than open duplicate incidents.

## Operator Note 4: Unknown Customer Impact
Unknown customer impact requires human review. Do not infer impact from severity alone when affectedService is missing or marked unknown.

## Operator Note 5: Enterprise Voice Routing
Enterprise Voice signaling and sip_trunk_failure alarms route to Voice NOC. Major Enterprise Voice outages use High impact and Medium urgency unless more than one site is down.

## Operator Note 6: VendorC Optical Validation
VendorC optical_degrade alarms often require manual validation. If historical evidence conflicts, route to Optical Assurance for clarification.
