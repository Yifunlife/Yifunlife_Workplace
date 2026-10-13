FROM node:24.19.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install --global pnpm@11.25.0
WORKDIR /app
COPY . .
RUN python3 prepare_source.py
RUN pnpm --dir modules/quote install --frozen-lockfile && pnpm --dir modules/procurement install --frozen-lockfile
RUN mkdir -p modules/aftersales/node_modules/.bin && ln -s /app/modules/procurement/node_modules/.bin/wrangler modules/aftersales/node_modules/.bin/wrangler
RUN python3 scripts/build_cloud_image.py
ENV YIFUN_CONTAINER_MODE=1 WRANGLER_SEND_METRICS=false
EXPOSE 8975 8991 8992 8993
CMD ["python3", "run_workplace.py", "--no-build", "--no-open"]
