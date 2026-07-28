FROM nginx:alpine

COPY docker/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf
COPY portal/dist /usr/share/nginx/portal
COPY frontend/dist /usr/share/nginx/admin
