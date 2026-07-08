FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

EXPOSE 3000
# ponytail: dev server, not a production build — this compose exists for local demo/review
CMD ["npm", "run", "dev"]
