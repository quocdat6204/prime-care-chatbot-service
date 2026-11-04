package com.example.chatbot.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDate;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ExamSessionDto {
    private Long id;
    private Long doctorId;
    private String doctorName;
    private String doctorRank;
    private String doctorAvatar;
    private String doctorPhone;
    private LocalDate examDate;
    private String shift;
    private BigDecimal examinationFee;
    private int maxPatients;
    private int lastQueueNumber;
    private String status;
    private Integer availableSlots;
}

