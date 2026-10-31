FROM nginx:alpine@sha256:62ff2089abf5a9ed33bd232895bef5e22f7bb4b200675cec49a5ebc48e3d4ac8

COPY docker/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf
COPY portal/dist /usr/share/nginx/portal
COPY frontend/dist /usr/share/nginx/admin
