package com.example.chatbot.service;

import com.example.chatbot.dto.ChatMessageDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

@Service
@Slf4j
@RequiredArgsConstructor
public class ChatSessionService {

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    private static final String KEY_PREFIX = "chat:history:";
    private static final Duration SESSION_TTL = Duration.ofHours(24);
    private static final long MAX_MESSAGES = 20;

    private String buildKey(String userId) {
        return KEY_PREFIX + (userId != null ? userId : "anonymous");
    }

    /**
     * Lưu tin nhắn vào Redis
     */
    public void saveMessage(String userId, ChatMessageDto message) {
        try {
            String key = buildKey(userId);
            String json = objectMapper.writeValueAsString(message);
            redisTemplate.opsForList().rightPush(key, json);

            // Giới hạn chỉ giữ tối đa 20 tin nhắn gần nhất
            redisTemplate.opsForList().trim(key, -MAX_MESSAGES, -1);

            // Gia hạn thời gian sống cho phiên chat (24 giờ)
            redisTemplate.expire(key, SESSION_TTL);
        } catch (Exception e) {
            log.warn("Không thể lưu tin nhắn vào Redis: {}", e.getMessage());
        }
    }

    /**
     * Lấy toàn bộ lịch sử tin nhắn của người dùng từ Redis
     */
    public List<ChatMessageDto> getHistory(String userId) {
        try {
            String key = buildKey(userId);
            List<String> rawList = redisTemplate.opsForList().range(key, 0, -1);
            if (rawList == null || rawList.isEmpty()) {
                return List.of();
            }

            List<ChatMessageDto> result = new ArrayList<>();
            for (String json : rawList) {
                result.add(objectMapper.readValue(json, ChatMessageDto.class));
            }
            return result;
        } catch (Exception e) {
            log.warn("Không thể lấy lịch sử chat từ Redis: {}", e.getMessage());
            return List.of();
        }
    }

    /**
     * Xóa sạch lịch sử trò chuyện của người dùng
     */
    public void clearHistory(String userId) {
        try {
            String key = buildKey(userId);
            redisTemplate.delete(key);
            log.info("Đã xóa lịch sử chat Redis của user: {}", userId);
        } catch (Exception e) {
            log.warn("Không thể xóa lịch sử chat Redis: {}", e.getMessage());
        }
    }

    /**
     * Tổng hợp ngữ cảnh 4-6 câu gần nhất để truyền vào Prompt của Gemini
     */
    public String getRecentContextForPrompt(String userId, int limit) {
        try {
            List<ChatMessageDto> history = getHistory(userId);
            if (history.isEmpty()) {
                return "Chưa có hội thoại trước đó.";
            }

            int start = Math.max(0, history.size() - limit);
            StringBuilder sb = new StringBuilder();
            for (int i = start; i < history.size(); i++) {
                ChatMessageDto msg = history.get(i);
                String role = "user".equalsIgnoreCase(msg.getSender()) ? "Bệnh nhân" : "Trợ lý AI";
                sb.append(String.format("- %s: %s\n", role, msg.getText()));
            }
            return sb.toString();
        } catch (Exception e) {
            return "Chưa có hội thoại trước đó.";
        }
    }
}

