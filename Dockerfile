FROM python:3.13-slim-bookworm AS builder

# Build dummy packages to skip installing them and their dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends equivs \
    && equivs-control libgl1-mesa-dri \
    && printf 'Section: misc\nPriority: optional\nStandards-Version: 3.9.2\nPackage: libgl1-mesa-dri\nVersion: 99.0.0\nDescription: Dummy package for libgl1-mesa-dri\n' >> libgl1-mesa-dri \
    && equivs-build libgl1-mesa-dri \
    && mv libgl1-mesa-dri_*.deb /libgl1-mesa-dri.deb \
    && equivs-control adwaita-icon-theme \
    && printf 'Section: misc\nPriority: optional\nStandards-Version: 3.9.2\nPackage: adwaita-icon-theme\nVersion: 99.0.0\nDescription: Dummy package for adwaita-icon-theme\n' >> adwaita-icon-theme \
    && equivs-build adwaita-icon-theme \
    && mv adwaita-icon-theme_*.deb /adwaita-icon-theme.deb

FROM python:3.13-slim-bookworm

# Copy dummy packages
COPY --from=builder /*.deb /

WORKDIR /app
    # Install dummy packages
RUN dpkg -i /libgl1-mesa-dri.deb \
    && dpkg -i /adwaita-icon-theme.deb \
    # Install dependencies with strictly pinned Chromium versions
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       chromium=147.0.7727.137-1~deb12u1 \
       chromium-common=147.0.7727.137-1~deb12u1 \
       chromium-driver=147.0.7727.137-1~deb12u1 \
       xvfb dumb-init procps curl vim xauth \
    # Remove temporary files and hardware decoding libraries
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/lib/*/libmfxhw* \
    && rm -f /usr/lib/*/mfx/* \
    # Create flaresolverr user
    && useradd --home-dir /app --shell /bin/sh flaresolverr \
    && mv /usr/bin/chromedriver chromedriver \
    && chown -R flaresolverr:flaresolverr . \
    # Create config dir
    && mkdir /config \
    && chown flaresolverr:flaresolverr /config

VOLUME /config

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt \
    # Remove temporary files
    && rm -rf /root/.cache

USER flaresolverr

RUN mkdir -p "/app/.config/chromium/Crash Reports/pending"

COPY src .
COPY package.json ../

EXPOSE 8191
EXPOSE 8192

# dumb-init avoids zombie chromium processes
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

CMD ["/usr/local/bin/python", "-u", "/app/flaresolverr.py"]