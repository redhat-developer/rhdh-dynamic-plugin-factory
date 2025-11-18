# https://registry.access.redhat.com/ubi9/nodejs-22
FROM registry.access.redhat.com/ubi9/nodejs-22-minimal:9.7-1763382208

# Runtime requirements and usage documentation
LABEL description="RHDH Dynamic Plugin Factory - Build and package Backstage plugins" \
      usage="podman run --rm -it --device /dev/fuse -v ./config:/config:z -v ./workspace:/workspace:z -v ./outputs:/outputs:z IMAGE_NAME" \
      io.podman.annotations.device="/dev/fuse" \
      io.podman.annotations.cap-add="SYS_ADMIN"

USER 0

WORKDIR /app
# Install corepack (not included in UBI images by default)
RUN npm install -g corepack

# Install necessary dependencies for building Node.js and other tools
RUN microdnf update -y  
RUN microdnf install -y --nodocs \
  --setopt=install_weak_deps=0 \
  --setopt=tsflags=nodocs \
  python3 git-core patch python3-pip make g++ zlib-devel \
  brotli-devel openssl-devel buildah bash patch jq fuse-overlayfs \
  && microdnf clean all

COPY requirements.txt .

# Install Python Dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /workspace /outputs /config


ENTRYPOINT ["python3", "-m", "src.rhdh_dynamic_plugin_factory"]
