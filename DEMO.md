# Aegis Rescue: Palisades Fire demo

## Scenario

Fire Station 6 is the fixed safe base outside the cumulative Palisades Fire footprint. Three rescue sites—N9, N15, and N21—begin inside the fire.

The demo repeats one clear operational loop:

1. Rank the waiting rescue sites using fire-distance priority and round-trip route cost.
2. Leave Fire Station 6 for one selected site.
3. Follow the lowest-cost route, balancing travel time against distance and duration inside fire.
4. Load the survivors at the site.
5. Return to Fire Station 6 before beginning another rescue.
6. Mark the site safe only after the responder reaches the station.

The mission ends after all three groups return to the station.

## Independent ambulance

A second vehicle starts at Hospital 14 and runs concurrently with the fire truck. It has its own position, route, fire-weight updates, medical-call queue, and blue/purple map styling.

The ambulance workflow is:

1. Leave Hospital 14 for the lowest-cost pending medical call.
2. Collect one person and continue directly to another call.
3. At 3/3 onboard, stop collecting and return to Hospital 14 automatically.
4. Unload all three people.
5. Resume the remaining medical-call route from the hospital.
6. Make a final hospital return when the queue is empty, even if below capacity.

The demo uses five medical calls so both the full-capacity return and post-drop-off route resumption are visible.

## Dynamic rerouting

Historical LAFD fire progression continues during each trip. Fire-exposed edges remain traversable, but their risk and travel-time weights rise for every interval spent inside the cumulative footprint.

The first eligible mid-travel update adds a small deterministic demo flare-up at the responder. The current road edge is replaced by a temporary yellow `LIVE N1000` node and proportional forward/backward segments. The optimizer compares:

- distance remaining toward the site or station;
- distance required to retreat;
- current fire exposure;
- alternate road costs;
- rescue-site priority.

This makes the continue-versus-retreat decision distance-dependent without restarting the responder from the previous node.

## Visual language

- Green marker: Fire Station 6
- Red markers: rescue sites inside fire
- Cyan route segments: clear travel
- Amber to red route segments: increasing fire exposure
- Dashed routes: second- and third-lowest-cost alternatives
- White/cyan marker: responder
- White/blue marker and blue-purple route: ambulance
- Blue marker: Hospital 14
- Purple markers: medical calls
- Yellow ring: temporary live split node

## Run

Open `http://127.0.0.1:5173`, click **Start rescue demo**, and watch each complete station-to-site-to-station cycle. Use **Reset** to restart the scenario.
