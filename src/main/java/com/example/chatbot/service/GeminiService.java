package com.example.chatbot.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
@Slf4j
public class GeminiService {

    @Value("${gemini.api-key:}")
    private String apiKey;

    @Value("${gemini.model:gemini-3.5-flash-lite}")
    private String model;

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public GeminiService(ObjectMapper objectMapper) {
        this.restClient = RestClient.builder().build();
        this.objectMapper = objectMapper;
    }

    /**
     * Gọi Google Gemini API để phân tích hoặc tạo nội dung
     *
     * @param prompt Nội dung yêu cầu AI
     * @param jsonOutput true nếu yêu cầu Gemini trả về JSON có cấu trúc (responseMimeType = application/json)
     * @return Chuỗi văn bản hoặc chuỗi JSON do Gemini phản hồi
     */
    public String generateContent(String prompt, boolean jsonOutput) {
        if (apiKey == null || apiKey.trim().isEmpty() || apiKey.startsWith("your-")) {
            log.warn("Gemini API key chưa được cấu hình. Vui lòng thiết lập biến môi trường GEMINI_API_KEY.");
            return jsonOutput
                    ? "{\"intent\":\"OUT_OF_SCOPE\",\"directReply\":\"Hệ thống chưa được thiết lập Google Gemini API Key. Vui lòng cấu hình GEMINI_API_KEY trong .env.\"}"
                    : "Dạ hiện tại hệ thống chatbot chưa được cấu hình khóa API Google Gemini. Bạn vui lòng liên hệ quản trị viên nhé!";
        }

        List<String> modelsToTry = new java.util.ArrayList<>();
        if (model != null && !model.isBlank()) {
            modelsToTry.add(model.trim());
        }
        if (!modelsToTry.contains("gemini-3.5-flash-lite")) {
            modelsToTry.add("gemini-3.5-flash-lite");
        }
        if (!modelsToTry.contains("gemini-flash-latest")) {
            modelsToTry.add("gemini-flash-latest");
        }

        Exception lastException = null;
        for (String targetModel : modelsToTry) {
            try {
                String result = callGemini(targetModel, prompt, jsonOutput);
                if (result != null && !result.isBlank()) {
                    return result;
                }
            } catch (Exception e) {
                lastException = e;
                log.warn("Lỗi khi gọi model [{}]: {}. Đang thử model dự phòng...", targetModel, e.getMessage());
            }
        }

        log.error("Tất cả model Gemini đều thất bại: {}", lastException != null ? lastException.getMessage() : "Unknown");
        return jsonOutput
                ? "{\"intent\":\"OUT_OF_SCOPE\",\"directReply\":\"Hiện tại không thể kết nối đến máy chủ AI Google.\"}"
                : "Dạ xin lỗi bạn, hiện tại kết nối đến trợ lý AI đang bận. Bạn vui lòng gửi lại câu hỏi sau giây lát nhé!";
    }

    private String callGemini(String targetModel, String prompt, boolean jsonOutput) throws Exception {
        String url = String.format(
                "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s",
                targetModel, apiKey
        );

        Map<String, Object> body = new HashMap<>();
        List<Map<String, Object>> contents = List.of(
                Map.of("parts", List.of(Map.of("text", prompt)))
        );
        body.put("contents", contents);

        if (jsonOutput) {
            body.put("generationConfig", Map.of("responseMimeType", "application/json"));
        }

        String responseJson = restClient.post()
                .uri(url)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(String.class);

        JsonNode root = objectMapper.readTree(responseJson);
        JsonNode candidates = root.path("candidates");
        if (candidates.isArray() && !candidates.isEmpty()) {
            JsonNode parts = candidates.get(0).path("content").path("parts");
            if (parts.isArray() && !parts.isEmpty()) {
                return parts.get(0).path("text").asText();
            }
        }

        return "";
    }
}

