package com.example.chatbot.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MedicalServiceDto {
    private Long id;
    private String name;
    private String serviceType;
    private BigDecimal price;
    private String roomNumber;
    private String description;
    private boolean active;
}

