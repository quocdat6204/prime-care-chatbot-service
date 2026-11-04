package com.example.chatbot.controller;

import com.example.chatbot.dto.ApiResponse;
import com.example.chatbot.dto.ChatMessageDto;
import com.example.chatbot.dto.ChatRequest;
import com.example.chatbot.dto.ChatResponse;
import com.example.chatbot.service.ChatbotService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/chatbot")
@RequiredArgsConstructor
public class ChatbotController {

    private final ChatbotService chatbotService;

    private String getCurrentUserId() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return (auth != null && auth.getName() != null) ? auth.getName() : "anonymous";
    }

    /**
     * API gửi tin nhắn hỏi đáp với Trợ lý AI Nha Khoa (Lưu lịch sử vào Redis)
     */
    @PostMapping("/message")
    public ApiResponse<ChatResponse> sendMessage(@RequestBody ChatRequest request) {
        String userId = getCurrentUserId();
        ChatResponse response = chatbotService.processMessage(request.getMessage(), userId);
        return ApiResponse.<ChatResponse>builder()
                .result(response)
                .build();
    }

    /**
     * API lấy toàn bộ lịch sử trò chuyện của người dùng từ Redis
     */
    @GetMapping("/history")
    public ApiResponse<List<ChatMessageDto>> getHistory() {
        String userId = getCurrentUserId();
        return ApiResponse.<List<ChatMessageDto>>builder()
                .result(chatbotService.getHistory(userId))
                .build();
    }

    /**
     * API xóa lịch sử trò chuyện trong Redis để làm mới cuộc hội thoại
     */
    @DeleteMapping("/history")
    public ApiResponse<String> clearHistory() {
        String userId = getCurrentUserId();
        chatbotService.clearHistory(userId);
        return ApiResponse.<String>builder()
                .result("Đã xóa lịch sử trò chuyện thành công!")
                .build();
    }

    /**
     * Health check endpoint
     */
    @GetMapping("/health")
    public ApiResponse<String> health() {
        return ApiResponse.<String>builder()
                .result("Chatbot Service is running smoothly on port 9004!")
                .build();
    }
}
