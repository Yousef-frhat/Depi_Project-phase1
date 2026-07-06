FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
COPY login.html /usr/share/nginx/html/login.html
COPY plans.html /usr/share/nginx/html/plans.html
COPY dashboard.html /usr/share/nginx/html/dashboard.html
COPY admin.html /usr/share/nginx/html/admin.html
COPY monitoring.html /usr/share/nginx/html/monitoring.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY logo.png /usr/share/nginx/html/logo.png
COPY vodafone.png /usr/share/nginx/html/vodafone.png
COPY orange.png /usr/share/nginx/html/orange.png
COPY we.png /usr/share/nginx/html/we.png
COPY etisalat.png /usr/share/nginx/html/etisalat.png
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
CMD ["/bin/sh", "-c", "envsubst '${BACKEND_HOST}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
