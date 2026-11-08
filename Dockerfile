# Stage 1: Build JAR
FROM maven:3.9.6-eclipse-temurin-17-alpine AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -B || true
COPY src ./src
RUN mvn clean package -DskipTests

# Stage 2: Runtime
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar

ENV JAVA_OPTS="-Xms128m -Xmx256m -XX:+UseG1GC -Duser.timezone=Asia/Ho_Chi_Minh"
EXPOSE 9004

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]

