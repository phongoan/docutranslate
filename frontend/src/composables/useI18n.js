import { ref } from 'vue';

export function useI18n() {
    const currentLang = ref(localStorage.getItem('ui_language') || 'vi');
    const i18nData = ref({});

    const t = (k, params) => {
        let v = i18nData.value[k] || k;
        if (params) {
            for (const [key, val] of Object.entries(params)) {
                v = v.replace(new RegExp(`\\{${key}\\}`, 'g'), String(val));
            }
        }
        return v;
    };

    const setLanguage = async (l) => {
        currentLang.value = l;
        localStorage.setItem('ui_language', l);
        document.documentElement.lang = l === 'zh' ? 'zh-CN' : (l === 'vi' ? 'vi' : 'en');
        // Reload i18n data
        try {
            const res = await fetch(`/static/i18n/${l}.json`);
            i18nData.value = await res.json();
        } catch (e) {
            console.error('Failed to load i18n:', e);
        }
    };

    const loadI18n = async () => {
        try {
            const lang = currentLang.value || 'vi';
            const res = await fetch(`/static/i18n/${lang}.json`);
            i18nData.value = await res.json();
        } catch (e) {
            // Fallback defaults
            i18nData.value = {
                pageTitle: "DocuTranslate - Dịch tài liệu tương tác",
                tutorialBtn: "Hướng dẫn",
                projectContributeBtn: "Hợp tác dự án",
                workflowTitle: "Chọn quy trình làm việc",
                autoWorkflowLabel: "Tự động chọn quy trình",
                workflowOptionPptx: "Thuyết trình PPTX (.pptx)",
                pptxSettingsTitleText: "Tùy chọn dịch PPTX",
                mineruDeployServerUrlLabel: "URL máy chủ",
                mineruDeployApiKeyLabel: "API Key dịch vụ cục bộ (tùy chọn)",
                mineruDeployApiKeyPlaceholder: "Để trống nếu không bật xác thực",
                mineruDeployApiKeyHelp: "Khóa truy cập dịch vụ phân tích MinerU tự triển khai, khác với Token trực tuyến và khóa mô hình dịch. Để trống để dùng biến môi trường máy chủ. Cấu hình môi trường bắt buộc được ưu tiên.",
                mineruDeployApiKeyShow: "Hiện khóa",
                mineruDeployApiKeyHide: "Ẩn khóa",
                mineruDeployLangListLabel: "Danh sách ngôn ngữ",
                mineruDeployServerUrlPlaceholder: "Ví dụ: http://127.0.0.1:30000",
                mineruDeployParseMethodLabel: "Phương pháp phân tích",
                mineruDeployTableEnableLabel: "Nhận dạng bảng"
            };
        }
    };

    return {
        currentLang,
        i18nData,
        t,
        setLanguage,
        loadI18n
    };
}
