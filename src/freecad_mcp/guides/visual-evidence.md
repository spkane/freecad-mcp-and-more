# Looking At What You Built

Pixels never substitute for a deterministic check, and a screenshot is not
evidence for a feature it does not clearly show. Follow this order.

## The Protocol

1. Run the deterministic structural and parametric checks first. Visual review
   supplements a passing model; it does not replace `validate_document` or a
   measurement. Pixels do not prove dimensions, connectivity, or editability —
   a render supports intent, but deterministic checks prove geometry.
2. Hide datum planes, origins, and construction helpers before capturing.
   Construction geometry left visible obscures the silhouette it was meant to
   support.
3. Capture one clean global view with `get_screenshot`.
4. For every semantic opening or profile — each door, each window, each
   lantern division — capture with `capture_feature_view` using that
   feature's own sketch or support as `normal_source`. A feature seen edge-on
   is not evidence about its shape; only a view along that feature's own
   normal shows whether it is the intended profile in the intended place.
5. Compare the silhouette against the profile you intended, and state the
   comparison explicitly. Do not describe an image as correct without saying
   what you compared it to.
6. Convert every visual concern into a deterministic geometry check. A shape
   that looks wrong in a render becomes a measurement, a solid-count check, or
   a bounding-box comparison, not a note that is never resolved.
7. If an opening is obstructed, edge-on, or absent from every retained image,
   say that you have no visual evidence for it. Do not report success for a
   feature you could not see.
8. Never describe an image you did not receive and inspect. A tool call that
   fails, times out, or returns no image content leaves no evidence, whatever
   the request looked like.
