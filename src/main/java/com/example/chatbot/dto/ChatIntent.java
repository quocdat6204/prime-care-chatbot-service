package com.example.chatbot.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class ChatIntent {

    /**
     * OUT_OF_SCOPE: Câu hỏi không liên quan nha khoa/phòng khám (thời tiết, lập trình, chính trị...)
     * CHECK_SCHEDULE: Hỏi lịch trực của bác sĩ hoặc ca khám theo ngày
     * CHECK_PRICE: Hỏi giá hoặc thông tin dịch vụ nha khoa
     * BOOKING_GUIDE: Hỏi cách đặt lịch khám
     * GENERAL: Chào hỏi, cảm ơn, tư vấn vệ sinh răng miệng cơ bản
     */
    private String intent;

    /** Tên bác sĩ mà người dùng nhắc tới (nếu có) */
    private String doctorName;

    /** Ngày định dạng YYYY-MM-DD được AI quy đổi từ "hôm nay", "ngày mai", "thứ 2"... */
    private String date;

    /** Tên dịch vụ (ví dụ: "nhổ răng khôn", "lấy cao răng", "trồng răng implant"...) */
    private String serviceName;

    /** Câu trả lời trực tiếp do AI tạo sẵn (đặc biệt khi OUT_OF_SCOPE hoặc GENERAL) */
    private String directReply;
}

