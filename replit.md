# UpTrack on Replit

- Run the Flask web application with `gunicorn --chdir app app:app --bind 0.0.0.0:5000`.
- The main portfolio dashboard is `/`. The preserved experimental public-data model page is `/research`.
- Personal-project delay checks are transparent rule-based assessments; the historical ML artifacts apply only to Research records. What-If scenarios are previews and must not write to project storage.
- User-managed projects are stored in `data/uptrack_projects.sqlite3`. This works across app restarts in the current workspace. Use durable shared storage before relying on records across production redeploys or multiple instances.
- The portfolio is a shared workspace and does not have sign-in or per-user access controls. Do not enter sensitive project information or publish it for private use until access control is added.
- Government project records remain on the Research page and are not copied into the personal portfolio.
