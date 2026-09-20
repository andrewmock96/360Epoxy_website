# Google reviews

The homepage carousel uses `/api/reviews`, backed by Places API (New).

- Set `GOOGLE_API_KEY` on the server with Places API (New) enabled. The key stays server-side.
- The default listing is 360Epoxy: `ChIJhQaI8w1vZ2QRyvapJkqxiak`. Override only with `GOOGLE_REVIEWS_PLACE_ID` if the listing changes. The old `GOOGLE_PLACE_ID` variable is no longer used because it pointed to Contec Supply.
- Reviews load when the visitor approaches the section. Google returns up to five reviews in relevance order; the overall rating and count cover the entire listing. No rating-based filtering is applied.
- Review data is not persisted or cached. The endpoint keeps its existing request limit, and failures retain a direct Google Maps link.
- Desktop shows three cards, tablets two, and phones one. Visitors can use the arrows, keyboard, or touch scrolling; there is no automatic rotation.

Run backend checks with `python -m unittest discover -s tests`. The local environment needs `FLASK_ENV=development`.
