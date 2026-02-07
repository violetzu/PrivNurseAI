FROM node:20-bookworm-slim

WORKDIR /frontend

COPY privnurse_gemma3n/frontend/ ./

RUN npm ci
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
