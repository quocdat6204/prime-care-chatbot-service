package com.example.chatbot.client;

import com.example.chatbot.dto.ApiResponse;
import com.example.chatbot.dto.ExamSessionDto;
import com.example.chatbot.dto.MedicalServiceDto;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

import java.time.LocalDate;
import java.util.List;

@FeignClient(name = "clinic-service")
public interface ClinicClient {

    @GetMapping("/internal/clinic/chatbot/sessions")
    ApiResponse<List<ExamSessionDto>> getSessions(
            @RequestParam("date") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date,
            @RequestParam(value = "doctorId", required = false) Long doctorId
    );

    @GetMapping("/internal/clinic/chatbot/services")
    ApiResponse<List<MedicalServiceDto>> getServices(
            @RequestParam(value = "keyword", required = false) String keyword
    );
}

