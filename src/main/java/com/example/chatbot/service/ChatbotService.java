package com.example.chatbot.service;

import com.example.chatbot.client.ClinicClient;
import com.example.chatbot.client.UserClient;
import com.example.chatbot.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

@Service
@Slf4j
@RequiredArgsConstructor
public class ChatbotService {

    private final GeminiService geminiService;
    private final ClinicClient clinicClient;
    private final UserClient userClient;
    private final ChatSessionService chatSessionService;
    private final ObjectMapper objectMapper;

    private static final DateTimeFormatter DATE_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter TIME_FORMATTER = DateTimeFormatter.ofPattern("HH:mm");

    public ChatResponse processMessage(String userMessage, String userId) {
        if (userMessage == null || userMessage.trim().isEmpty()) {
            return ChatResponse.builder()
                    .reply("Dạ, bạn cần hỗ trợ thông tin gì về dịch vụ nha khoa hay lịch khám ạ?")
                    .intent("GENERAL")
                    .suggestions(List.of("Bác sĩ nào trực hôm nay?", "Bảng giá nhổ răng khôn", "Hướng dẫn đặt lịch khám"))
                    .build();
        }

        String currentTimeStr = LocalTime.now().format(TIME_FORMATTER);

        // 1. Lưu tin nhắn của bệnh nhân vào Redis
        chatSessionService.saveMessage(userId, ChatMessageDto.builder()
                .sender("user")
                .text(userMessage.trim())
                .time(currentTimeStr)
                .build());

        // 2. Lấy 4 lượt hội thoại gần nhất từ Redis để AI hiểu ngữ cảnh liên tục
        String recentContext = chatSessionService.getRecentContextForPrompt(userId, 4);

        LocalDate today = LocalDate.now();

        // 3. Lấy danh sách bác sĩ từ user-service để AI đối chiếu chính xác
        List<DoctorSummaryDto> doctors = getDoctorsList();
        String doctorNames = doctors.stream()
                .map(d -> String.format("%s (ID: %d)", d.getFullName(), d.getId()))
                .reduce((a, b) -> a + ", " + b)
                .orElse("Chưa có danh sách");

        // 4. BƯỚC 1: NHỜ GEMINI PHÂN TÍCH Ý ĐỊNH VÀ TRÍCH XUẤT THỰC THỂ (CÓ KÈM NGỮ CẢNH REDIS)
        String step1Prompt = String.format("""
            Bạn là Trợ lý AI của Hệ thống Phòng Khám Nha Khoa & Y tế Primecare Dental.
            Thời điểm hiện tại: %s (Hôm nay).
            Danh sách bác sĩ của phòng khám: [%s].
            Các nhóm dịch vụ phòng khám cung cấp bao gồm:
            - Nha khoa điều trị & thẩm mỹ (khám răng, lấy cao răng, nhổ răng khôn, niềng răng, bọc răng sứ, trám răng...)
            - Cận lâm sàng & Xét nghiệm: Xét nghiệm công thức máu toàn bộ (CBC), kiểm tra máu và viêm nhiễm...
            - Chẩn đoán hình ảnh: Chụp X-quang lồng ngực/răng hàm, Siêu âm màu ổ bụng tổng quát...
            - Dịch vụ khám và điều trị khác.

            Lịch sử trò chuyện gần nhất giữa bệnh nhân và trợ lý AI:
            %s

            Nhiệm vụ: Hãy phân tích câu hỏi mới nhất của bệnh nhân: "%s" và trả về JSON:
            {
              "intent": "OUT_OF_SCOPE | CHECK_SCHEDULE | CHECK_SERVICE | BOOKING_GUIDE | GENERAL",
              "doctorName": "Họ tên bác sĩ nếu có trong câu hỏi HOẶC được nhắc ở ngữ cảnh trước đó, nếu không thì null",
              "date": "Ngày định dạng YYYY-MM-DD nếu hỏi hôm nay, ngày mai, thứ mấy... (dựa theo ngày hiện tại %s), nếu không thì null",
              "serviceName": "Tên hoặc từ khóa dịch vụ/xét nghiệm/chụp chiếu/thủ thuật nếu có trong câu hỏi hoặc ngữ cảnh trước đó, nếu không thì null",
              "directReply": "Câu trả lời trực tiếp nếu là OUT_OF_SCOPE hoặc GENERAL hoặc chào hỏi"
            }

            QUY TẮC QUAN TRỌNG:
            1. Ý định tra cứu dịch vụ / giá cả / cận lâm sàng / xét nghiệm (CHECK_SERVICE):
               - MỌI câu hỏi hỏi phòng khám CÓ dịch vụ này không (ví dụ: có xét nghiệm không, có xét nghiệm máu không, có chụp X-quang không, có siêu âm không, có nhổ răng không...), hoặc hỏi giá, hỏi phòng thực hiện -> BẮT BUỘC gán intent là "CHECK_SERVICE".
               - Trích xuất từ khóa dịch vụ vào "serviceName" (ví dụ: "xét nghiệm", "xét nghiệm máu", "x-quang", "siêu âm", "lấy cao răng"...).
               - ĐỂ "directReply" là null (vì hệ thống sẽ tự động tra cứu dữ liệu thực tế từ phòng khám ở Bước 2).
            2. Ý định tra cứu lịch trực bác sĩ / ca khám (CHECK_SCHEDULE):
               - Khi hỏi về bác sĩ trực, ca sáng/chiều, ngày khám... -> Gán intent là "CHECK_SCHEDULE".
            3. Ý định hỏi cách đặt lịch (BOOKING_GUIDE):
               - Khi hỏi các bước đặt lịch, cách giữ chỗ khám trực tuyến... -> Gán intent là "BOOKING_GUIDE".
            4. Ý định chào hỏi / cảm ơn (GENERAL):
               - Chào hỏi ("xin chào", "hello"), cảm ơn -> Gán intent là "GENERAL", directReply là câu chào đón niềm nở và sẵn sàng hỗ trợ.
            5. Ý định ngoài phạm vi (OUT_OF_SCOPE):
               - CHỈ gán OUT_OF_SCOPE khi câu hỏi HOÀN TOÀN KHÔNG LIÊN QUAN ĐẾN Y TẾ / PHÒNG KHÁM (ví dụ: hỏi code lập trình, thời tiết hôm nay, chính trị, bóng đá, nấu ăn, chơi game...).
               - Gán directReply bằng câu từ chối lịch sự, ví dụ: "Dạ xin lỗi bạn, tôi là Trợ lý AI của phòng khám. Tôi chỉ có thể hỗ trợ các thông tin về dịch vụ khám, xét nghiệm, chụp chiếu, bác sĩ và đặt lịch hẹn thôi ạ!"
            6. Tận dụng "Lịch sử trò chuyện gần nhất" để nhận diện đối tượng đang nhắc tới (nếu trước đó hỏi về một dịch vụ/bác sĩ, câu sau hỏi tiếp).
            """, today, doctorNames, recentContext, userMessage, today);

        ChatIntent intentDto;
        try {
            String jsonOutput = geminiService.generateContent(step1Prompt, true);
            intentDto = objectMapper.readValue(jsonOutput, ChatIntent.class);
        } catch (Exception e) {
            log.error("Lỗi parse ChatIntent từ Gemini: {}", e.getMessage());
            intentDto = ChatIntent.builder()
                    .intent("GENERAL")
                    .directReply("Dạ, phòng khám nha khoa có thể giúp gì cho bạn về thăm khám và bảng giá ạ?")
                    .build();
        }

        log.info("AI trích xuất Intent: {}, Bác sĩ: {}, Ngày: {}, Dịch vụ: {}",
                intentDto.getIntent(), intentDto.getDoctorName(), intentDto.getDate(), intentDto.getServiceName());

        // 5. BƯỚC 2: XỬ LÝ THEO TỪNG INTENT
        String finalReply;
        List<String> suggestions = new ArrayList<>();

        switch (intentDto.getIntent() != null ? intentDto.getIntent() : "GENERAL") {
            case "OUT_OF_SCOPE":
            case "GENERAL":
                // Câu hỏi ngoài phạm vi hoặc chào hỏi -> Trả lời ngay không cần query DB!
                finalReply = intentDto.getDirectReply() != null
                        ? intentDto.getDirectReply()
                        : "Dạ, tôi có thể hỗ trợ bạn kiểm tra lịch bác sĩ hoặc bảng giá dịch vụ nha khoa ạ!";
                suggestions = List.of("Bác sĩ trực hôm nay", "Bảng giá lấy cao răng", "Lịch khám ngày mai");
                break;

            case "BOOKING_GUIDE":
                finalReply = "Để đặt lịch khám nha khoa trực tuyến, bạn có thể vào mục **Ca Khám** trên hệ thống:\n" +
                             "1. Chọn **Đặt theo ngày** (nếu bạn muốn chọn ngày khám trước).\n" +
                             "2. Hoặc chọn **Đặt theo bác sĩ** (để xem trọn vẹn lịch 5 ngày tới của bác sĩ bạn tin tưởng).\n" +
                             "3. Chọn ca khám phù hợp (Ca Sáng 08:00 - 12:00 hoặc Ca Chiều 13:30 - 17:30) và xác nhận giữ chỗ nhé!";
                suggestions = List.of("Xem lịch trực hôm nay", "Bác sĩ trực 5 ngày tới", "Bảng giá dịch vụ");
                break;

            case "CHECK_SCHEDULE":
                finalReply = handleCheckSchedule(intentDto, doctors, userMessage, today);
                suggestions = List.of("Đặt lịch khám ngay", "Bác sĩ khác trực hôm nay", "Bảng giá khám");
                break;

            case "CHECK_SERVICE":
            case "CHECK_PRICE":
                finalReply = handleCheckService(intentDto, userMessage);
                suggestions = List.of("Đặt lịch khám ngay", "Xem dịch vụ khác", "Bác sĩ trực hôm nay");
                break;

            default:
                finalReply = "Dạ phòng khám nha khoa có thể hỗ trợ gì cho bạn về bác sĩ, ca trực và bảng giá hôm nay ạ?";
                suggestions = List.of("Bác sĩ trực hôm nay", "Bảng giá dịch vụ", "Hướng dẫn đặt lịch");
                break;
        }

        // 6. Lưu câu trả lời của Bot vào Redis
        chatSessionService.saveMessage(userId, ChatMessageDto.builder()
                .sender("bot")
                .text(finalReply)
                .time(LocalTime.now().format(TIME_FORMATTER))
                .suggestions(suggestions)
                .build());

        return ChatResponse.builder()
                .reply(finalReply)
                .intent(intentDto.getIntent())
                .suggestions(suggestions)
                .build();
    }

    /**
     * Lấy toàn bộ lịch sử trò chuyện của user từ Redis
     */
    public List<ChatMessageDto> getHistory(String userId) {
        return chatSessionService.getHistory(userId);
    }

    /**
     * Xóa lịch sử trò chuyện của user trong Redis
     */
    public void clearHistory(String userId) {
        chatSessionService.clearHistory(userId);
    }

    /**
     * Xử lý tra cứu lịch trực bác sĩ và tổng hợp bằng AI (Gọi qua OpenFeign sang clinic-service)
     */
    private String handleCheckSchedule(ChatIntent intent, List<DoctorSummaryDto> doctors, String userQuestion, LocalDate today) {
        LocalDate targetDate = today;
        if (intent.getDate() != null) {
            try {
                targetDate = LocalDate.parse(intent.getDate(), DATE_FORMATTER);
            } catch (Exception ignored) {}
        }

        // Tìm doctorId nếu người dùng nhắc tên bác sĩ
        Long doctorId = null;
        if (intent.getDoctorName() != null) {
            String lowerName = intent.getDoctorName().toLowerCase();
            for (DoctorSummaryDto d : doctors) {
                if (d.getFullName() != null && d.getFullName().toLowerCase().contains(lowerName)) {
                    doctorId = d.getId();
                    break;
                }
            }
        }

        // Gọi sang clinic-service qua Feign Client
        List<ExamSessionDto> sessions = List.of();
        try {
            ApiResponse<List<ExamSessionDto>> res = clinicClient.getSessions(targetDate, doctorId);
            if (res != null && res.getResult() != null) {
                sessions = res.getResult();
            }
        } catch (Exception e) {
            log.error("Lỗi khi gọi clinic-service lấy ca khám qua Feign: {}", e.getMessage());
        }

        String contextData;
        if (sessions.isEmpty()) {
            contextData = String.format("Ngày %s: Hiện tại KHÔNG CÓ ca khám nào mở (hoặc bác sĩ không có ca trực trong ngày này).", targetDate);
        } else {
            StringBuilder sb = new StringBuilder();
            sb.append(String.format("Dữ liệu các ca khám ngày %s:\n", targetDate));
            for (ExamSessionDto sess : sessions) {
                String docName = sess.getDoctorName() != null ? sess.getDoctorName() : ("Bác sĩ #" + sess.getDoctorId());
                String shift = "MORNING".equalsIgnoreCase(sess.getShift()) ? "Ca Sáng (08:00 - 12:00)" : "Ca Chiều (13:30 - 17:30)";
                int slots = sess.getAvailableSlots() != null ? sess.getAvailableSlots() : Math.max(0, sess.getMaxPatients() - sess.getLastQueueNumber());
                String fee = sess.getExaminationFee() != null ? String.format("%,.0f đ", sess.getExaminationFee()) : "150.000 đ";
                sb.append(String.format("- Bác sĩ: %s | Khung giờ: %s | Chỗ còn trống: %d/%d chỗ | Phí khám: %s\n",
                        docName, shift, slots, sess.getMaxPatients(), fee));
            }
            contextData = sb.toString();
        }

        // Bước tổng hợp câu trả lời bằng Gemini
        String step2Prompt = String.format("""
            Bạn là Trợ lý AI của Phòng Khám Nha Khoa.
            Người dùng đã hỏi: "%s"
            Dữ liệu lịch khám thực tế từ hệ thống:
            %s

            Hãy tổng hợp thành một câu trả lời tự nhiên, ân cần, ngắn gọn và đầy đủ thông tin cho bệnh nhân.
            Nếu còn chỗ khám, hãy nhắc bệnh nhân vào trang Ca Khám để giữ chỗ nhé!
            """, userQuestion, contextData);

        return geminiService.generateContent(step2Prompt, false);
    }

    /**
     * Xử lý tra cứu dịch vụ/xét nghiệm/bảng giá và tổng hợp bằng AI (Gọi qua OpenFeign sang clinic-service)
     */
    private String handleCheckService(ChatIntent intent, String userQuestion) {
        String keyword = intent.getServiceName();
        List<MedicalServiceDto> services = List.of();
        try {
            ApiResponse<List<MedicalServiceDto>> res = clinicClient.getServices(keyword);
            if (res != null && res.getResult() != null) {
                services = res.getResult();
            }
        } catch (Exception e) {
            log.error("Lỗi khi gọi clinic-service lấy dịch vụ qua Feign: {}", e.getMessage());
        }

        String contextData;
        if (services.isEmpty()) {
            contextData = keyword != null && !keyword.isBlank()
                    ? String.format("Hệ thống phòng khám hiện TẠM THỜI CHƯA CÓ dịch vụ phù hợp với từ khóa '%s'.", keyword)
                    : "Hiện tại hệ thống chưa tải được danh mục dịch vụ.";
        } else {
            StringBuilder sb = new StringBuilder("Dữ liệu dịch vụ thực tế tìm thấy từ danh mục phòng khám:\n");
            for (MedicalServiceDto s : services) {
                String priceStr = s.getPrice() != null ? String.format("%,.0f VNĐ", s.getPrice()) : "Liên hệ";
                String typeStr = "LAB_TEST".equals(s.getServiceType()) ? "Xét nghiệm"
                        : ("IMAGING".equals(s.getServiceType()) ? "Chẩn đoán hình ảnh" : "Nha khoa");
                sb.append(String.format("- Tên dịch vụ: %s | Phân loại: %s | Đơn giá: %s | Phòng thực hiện: %s | Mô tả: %s\n",
                        s.getName(),
                        typeStr,
                        priceStr,
                        s.getRoomNumber() != null ? s.getRoomNumber() : "Phòng điều trị",
                        s.getDescription() != null ? s.getDescription() : "Không có"));
            }
            contextData = sb.toString();
        }

        // Bước tổng hợp câu trả lời bằng Gemini
        String step2Prompt = String.format("""
            Bạn là Trợ lý AI của Hệ thống Phòng Khám Nha Khoa & Y tế Primecare Dental.
            Người dùng đã hỏi: "%s"
            Dữ liệu dịch vụ thực tế từ hệ thống phòng khám:
            %s

            Nhiệm vụ:
            - Dựa trên dữ liệu dịch vụ thực tế trên, hãy trả lời câu hỏi của người dùng một cách chính xác, ân cần và chuyên nghiệp.
            - Nếu phòng khám CÓ dịch vụ (ví dụ Xét nghiệm công thức máu toàn bộ (CBC), chụp X-quang, lấy cao răng...): Hãy khẳng định rõ ràng phòng khám CÓ dịch vụ này, nêu rõ tên đầy đủ, đơn giá niêm yết, phòng thực hiện và mô tả/công dụng tóm tắt.
            - Nếu phòng khám KHÔNG CÓ dịch vụ: Hãy thông báo lịch sự rằng phòng khám hiện chưa triển khai dịch vụ này và tư vấn dịch vụ liên quan nếu có.
            - Nhắc bệnh nhân có thể đặt lịch hẹn khám trước hoặc đến trực tiếp phòng khám để được phục vụ chu đáo nhất.
            """, userQuestion, contextData);

        return geminiService.generateContent(step2Prompt, false);
    }

    private List<DoctorSummaryDto> getDoctorsList() {
        try {
            ApiResponse<List<DoctorSummaryDto>> response = userClient.getDoctors();
            if (response != null && response.getResult() != null) {
                return response.getResult();
            }
        } catch (Exception e) {
            log.warn("Không thể lấy danh sách bác sĩ từ user-service qua Feign: {}", e.getMessage());
        }
        return List.of();
    }
}
