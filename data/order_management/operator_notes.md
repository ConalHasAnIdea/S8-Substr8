# Order Management Operator Notes

## Operator Note OM1: Residential and Enterprise Reservation
Residential and Enterprise orders reserve inventory differently. Enterprise Ethernet normally reserves a service instance and circuit resource, while Residential Broadband reserves an access resource tied to the site address.

## Operator Note OM2: Disconnect Dependency Check
Disconnect orders must verify there are no dependent service instances before inventory is released or decommissioned.

## Operator Note OM3: Sparse Fulfillment Evidence
If bandwidth or access technology evidence is sparse, route the mapping for clarification rather than inferring a logical device from product text alone.
