# https://registry.access.redhat.com/ubi9/nodejs-22
FROM registry.access.redhat.com/ubi9/nodejs-22:9.6-1760386551

# Runtime requirements and usage documentation
LABEL description="RHDH Dynamic Plugin Factory - Build and package Backstage plugins" \
      usage="podman run --rm -it --device /dev/fuse -v ./config:/config:z -v ./workspace:/workspace:z -v ./outputs:/outputs:z IMAGE_NAME" \
      io.podman.annotations.device="/dev/fuse" \
      io.podman.annotations.cap-add="SYS_ADMIN"

USER 0

WORKDIR /app

COPY . .
# Install corepack (not included in UBI images by default)
RUN npm install -g corepack

# Install necessary dependencies for building Node.js and other tools
RUN dnf update -y  
RUN dnf install  -q -y --allowerasing --nobest python3 git patch python3-pip python3-devel \
  make g++ zlib-devel brotli-devel openssl-devel buildah bash patch jq

# Install Python Dependencies
RUN pip install -r requirements.txt

RUN mkdir -p /workspace
RUN mkdir -p /outputs
RUN mkdir -p /config


ENTRYPOINT ["python3", "-m", "src.rhdh_dynamic_plugin_factory.cli"]
