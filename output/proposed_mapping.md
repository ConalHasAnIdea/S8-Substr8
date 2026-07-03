# Proposed Substr8 Mapping

## perceivedSeverity
- Destinations: impact, urgency
- Confidence: 0.82
- Status: Needs Clarification
- Citations: TKT-1001, TKT-1002, TKT-1003, TKT-1004, TKT-1005, TKT-1006, TKT-1007, TKT-1008, TKT-1009, TKT-1010, TKT-1011, TKT-1012, TKT-1026, TKT-1015, TKT-1016, TKT-1017, TKT-1023, TKT-1024, TKT-1029, TKT-1021, TKT-1022, TKT-1027, TKT-1028, TKT-1013, TKT-1014, TKT-1018, TKT-1019, TKT-1020, TKT-1025, TKT-1030, Operator Note 2, Operator Note 4, Legacy Rule 1, Legacy Rule 2

Derived from 30 historical severity examples: 23 support the selected impact/urgency outcomes and 7 conflict or were later corrected. Conflicting cases (TKT-1013, TKT-1014, TKT-1018, TKT-1019, TKT-1020, TKT-1025, TKT-1030) reduced confidence. Operator Note 2 reinforces the critical alarm handling policy. Note authority: Operator Note 2 (Jordan Reyes, Client Operations Lead, authority 1.0); Operator Note 4 (Jordan Reyes, Client Operations Lead, authority 1.0). Authority weighting from Operator Note 2, Operator Note 4 averaged 1.00, adjusting confidence from 0.77 to 0.82. ServiceNow priority is derived downstream from the operator impact x urgency matrix.

## probableCause=duplicate_alarm
- Destinations: assignment_group
- Confidence: 0.59
- Status: Needs Clarification
- Citations: TKT-1029, Operator Note 3

Derived from 1 historical duplicate_alarm tickets: 1 support assignment_group=Transport NOC and 0 conflict or were corrected. The leading outcome appeared in 1 correct tickets. Operator context included Operator Note 3. Note authority: Operator Note 3 (Priya Nair, Integration Architect, authority 0.9). Authority weighting from Operator Note 3 averaged 0.90, adjusting confidence from 0.55 to 0.59.

## probableCause=equipment_malfunction
- Destinations: assignment_group
- Confidence: 0.6
- Status: Needs Clarification
- Citations: TKT-1018, TKT-1021

Derived from 2 historical equipment_malfunction tickets: 2 support assignment_group=Access NOC and 0 conflict or were corrected. The leading outcome appeared in 2 correct tickets.

## probableCause=link_down
- Destinations: assignment_group
- Confidence: 0.86
- Status: Needs Clarification
- Citations: TKT-1001, TKT-1002, TKT-1003, TKT-1004, TKT-1005, TKT-1006, TKT-1007, TKT-1008, TKT-1009, TKT-1010, TKT-1012, TKT-1015, TKT-1016, TKT-1017, TKT-1027, TKT-1013, TKT-1014, Legacy Rule 3, Legacy Rule 4, Operator Note 1, Legacy Rule 3, Legacy Rule 4

Derived from 17 historical link_down tickets: 15 support assignment_group=Transport NOC and 3 conflict or were corrected. The leading outcome appeared in 15 correct tickets. Conflicting citations: TKT-1013, TKT-1014, Legacy Rule 3, Legacy Rule 4. Operator context included Operator Note 1. Note authority: Operator Note 1 (Sam Whitfield, Network SME, authority 0.85). Authority weighting from Operator Note 1 averaged 0.85, adjusting confidence from 0.83 to 0.86. Legacy rules disagree with each other, so policy should require review.

## probableCause=optical_degrade
- Destinations: assignment_group
- Confidence: 0.5
- Status: Needs Clarification
- Citations: TKT-1011, TKT-1019, TKT-1028, TKT-1020, Operator Note 6, Legacy Rule 7

Derived from 4 historical optical_degrade tickets: 3 support assignment_group=Optical Assurance and 1 conflict or were corrected. The leading outcome appeared in 3 correct tickets. Conflicting citations: TKT-1020. Operator context included Operator Note 6. Note authority: Operator Note 6 (Avery Brooks, Vendor Support Analyst, authority 0.3). Authority weighting from Operator Note 6 averaged 0.30, adjusting confidence from 0.52 to 0.50.

## probableCause=packet_loss
- Destinations: assignment_group
- Confidence: 0.55
- Status: Needs Clarification
- Citations: TKT-1022

Derived from 1 historical packet_loss tickets: 1 support assignment_group=Transport NOC and 0 conflict or were corrected. The leading outcome appeared in 1 correct tickets.

## probableCause=power_failure
- Destinations: assignment_group
- Confidence: 0.6
- Status: Needs Clarification
- Citations: TKT-1025, TKT-1026, Legacy Rule 6

Derived from 2 historical power_failure tickets: 2 support assignment_group=Field Operations and 0 conflict or were corrected. The leading outcome appeared in 2 correct tickets.

## probableCause=sip_trunk_failure
- Destinations: assignment_group
- Confidence: 0.64
- Status: Needs Clarification
- Citations: TKT-1023, TKT-1024, Operator Note 5, Legacy Rule 9

Derived from 2 historical sip_trunk_failure tickets: 2 support assignment_group=Voice NOC and 0 conflict or were corrected. The leading outcome appeared in 2 correct tickets. Operator context included Operator Note 5. Note authority: Operator Note 5 (Sam Whitfield, Network SME, authority 0.85). Authority weighting from Operator Note 5 averaged 0.85, adjusting confidence from 0.60 to 0.64.

## probableCause=solar_flare_noise
- Destinations: assignment_group
- Confidence: None
- Status: Insufficient Evidence - Human Required
- Citations: none

No historical tickets, operator notes, or legacy rules mention probableCause=solar_flare_noise. The mock engine refuses to fabricate a mapping and routes this value to a human.

## probableCause=unknown_failure
- Destinations: assignment_group
- Confidence: 0.0
- Status: Needs Clarification
- Citations: TKT-1030

Derived from 1 historical unknown_failure tickets: 0 support assignment_group=Human Review and 1 conflict or were corrected. Conflicting citations: TKT-1030.
