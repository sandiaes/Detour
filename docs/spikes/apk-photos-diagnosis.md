# Why the APK shows no photos (2026-11-14)

Part 0 of `docs/briefs/multi-city-trips-and-photos.md`. Checked against the real Supabase project
and the repository's history; the Render service itself could not be reached from the session
(its host is outside the session's network allowlist), so the API's answers were not observed.

## Findings

| Check | Result |
|---|---|
| Photo rows and files | 114 rows in `geo.image`, none hidden; all 114 files in the `photos` bucket (public, JPEG only, 2 MB limit) |
| Covers for the owner's trips | Vienna (`2761369`) and Salzburg (`2766824`) each have a `found` city lookup, so `GET /v1/trips` returns a `cover_image` for them |
| APK version | "Android APK" runs 11 to 15 were built from `main` after `28c5817` and `893a133` merged; the latest (run 15) is `32600ca` |
| Supabase project | `ACTIVE_HEALTHY`, not paused |
| `GET /v1/images/{id}` on Render | **Most likely 503.** The commit that declared `DETOUR_SUPABASE_URL` and `DETOUR_SUPABASE_SERVICE_KEY` in `render.yaml` and wrote the deployment steps (`9425687`) was pushed a minute after PR #29 merged and never reached `main`. Without both variables `make_store` returns nothing and the endpoint answers 503 `images_unavailable`; the app then draws only the photo's average colour |
| Attraction photos | The resolver looked up only a sample: of the 42 visits in the owner's Vienna plan, 10 were looked up and 4 have a photo; none of the 16 Salzburg visits was looked up; meals are never looked up. So even with storage working, most stops show no photo |

## Fault fixed

`9425687` is cherry-picked onto this branch (`render.yaml` and the "Deploying photos" steps in
`docs/deployment.md`). The owner still has to set the two variables in the Render dashboard
(Environment tab of `detour-api`); a Blueprint never carries a secret value. Then
`/v1/images/9a49af3b-9dfb-5a0c-8637-6bb38eb7341b` (Vienna's cover) should answer a JPEG.

## Not a fault, but the cause of few attraction photos

Coverage of planned places is a resolver-scope problem, which Part 2c (resolve the trip's places in
the background after generation) addresses.
