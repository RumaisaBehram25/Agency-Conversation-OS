# ============================================
# Attora Frontend — Nginx Placeholder
# (Real React frontend will be built in feature-004)
# ============================================
FROM nginx:1.27-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create placeholder index page
RUN mkdir -p /usr/share/nginx/html && \
    echo '<!DOCTYPE html><html><head><title>Attora</title></head><body><h1>Attora MVP</h1><p>Frontend placeholder. The React dashboard will be built in feature-004.</p></body></html>' \
    > /usr/share/nginx/html/index.html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
