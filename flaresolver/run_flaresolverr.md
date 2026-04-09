## Using docker-compose (Recommended)

All config (ports, volumes, env vars) is defined in docker-compose.yml — no need to remember flags.

### Build & Run:
- cd FlareSolverr
- docker-compose up -d --build

--build -> Builds the image before starting (use this after code changes)
-d -> Run in detached mode (background)

### Stop:
- docker-compose down

### View Logs:
- docker-compose logs -f

-f -> Follow/stream logs in real-time

---

## Using docker run (Manual)

You manage all flags yourself. docker-compose.yml is NOT used.

### Build Image Command:
- cd FlareSolverr
- docker build -t flaresolverr .

-t -> tag
Create a Image with tag(name) flaresolverr
Added a dot . at the end of the command to specify the current directory as the build context.

### Run Image as Container Command:
- docker run -d -p 8191:8191 -v ./config:/config --name flaresolverr flaresolverr

-d -> Run in detached mode
-p -> Port mapping
-v -> Mount local ./config folder to /config inside container (persists db.json)
--name -> Name of the container

Create a container named X from image X
A "config" folder will appear in your current directory with post2_db.json

### Stop Container:
- docker stop flaresolverr

### Remove Container (required before re-running):
- docker rm flaresolverr

### PUSH TO GITHUB

docker build -t ghcr.io/rishi058/flaresolverr .

docker push ghcr.io/rishi058/flaresolverr