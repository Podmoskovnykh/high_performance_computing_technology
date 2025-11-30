#!/bin/sh
set -e

# Remove default template processing to avoid conflicts
rm -f /etc/nginx/templates/nginx.conf.template

# Substitute HOSTNAME_FQDN environment variable in mounted nginx.conf
if [ -f /etc/nginx/nginx.conf.template ]; then
    # First substitute the placeholder in sub_filter with actual value
    sed "s|HOSTNAME_FQDN_VALUE|${HOSTNAME_FQDN:-localhost}|g" /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
    echo "Substituted HOSTNAME_FQDN=${HOSTNAME_FQDN:-localhost} in nginx.conf"
fi

# Execute default nginx entrypoint
exec /docker-entrypoint.sh nginx -g "daemon off;"

