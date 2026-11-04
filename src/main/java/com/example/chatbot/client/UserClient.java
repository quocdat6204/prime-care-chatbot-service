package com.example.chatbot.client;

import com.example.chatbot.dto.ApiResponse;
import com.example.chatbot.dto.DoctorSummaryDto;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

import java.util.List;

@FeignClient(name = "user-service")
public interface UserClient {

    @GetMapping("/users/doctors")
    ApiResponse<List<DoctorSummaryDto>> getDoctors();
}

