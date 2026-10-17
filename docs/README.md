# Benchmark website

The static site is published from this folder. It uses no API keys, analytics, remote fonts or paid services. Assets use relative paths and work at `https://OWNER.github.io/REPOSITORY/`.

For a local preview, from the repository root:

```sh
python -m http.server 8000 --directory docs
```

Visit `http://localhost:8000/`. You can also open `docs/index.html` directly.

In GitHub **Settings → Pages**, choose **Deploy from a branch**, then `main` and `/docs`. Alternatively choose **GitHub Actions** to use `.github/workflows/pages.yml`.

Fill in `docs/site-config.js` with the public paper link, repository link and final BibTeX. The page keeps those links visibly forthcoming until configured.

To regenerate the site's numerical data and task catalog from the frozen evidence:

```sh
python -B scripts/build_website_data.py --source redcommerce/data --output docs
```

The builder recomputes four-model statistics from 3,316 records and checks the counts against the paper. It exports all 96 task instructions and variant counts. Scientific interpretation is retained in the page and repository documentation.
