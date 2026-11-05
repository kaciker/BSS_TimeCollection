# Frontend deployment policy

The former static release context built a web image from a partial prebuilt dist directory. It omitted company logos and is retired. The only supported frontend build is frontend/Dockerfile from this repository frontend context; it installs from the lockfile, runs frontend tests, builds the app, and verifies required public assets before an image can be produced.

Deployments use the source commit as the image revision and replace only the web service. Never ship a hand assembled dist directory.
