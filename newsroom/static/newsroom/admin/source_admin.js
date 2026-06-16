(function ($) {
    "use strict";

    const CATEGORIES_URL = "/admin/newsroom/source/categories-by-site/";

    function updateCategories(siteId, selectedId) {
        const $select = $("#id_target_category");
        $select.empty().append('<option value="">---------</option>');
        if (!siteId) return;

        $.getJSON(CATEGORIES_URL, { site_id: siteId }, function (data) {
            data.categories.forEach(function (cat) {
                const $opt = $("<option>").val(cat.id).text(cat.name);
                if (selectedId && cat.id === selectedId) {
                    $opt.prop("selected", true);
                }
                $select.append($opt);
            });
        });
    }

    $(document).ready(function () {
        const $siteSelect = $("#id_target_site");

        $siteSelect.on("change", function () {
            updateCategories($(this).val(), null);
        });

        // On edit form load: site is already selected — reload categories
        // so the dropdown stays consistent even if site is changed before save.
        const initSite = $siteSelect.val();
        if (initSite) {
            const initCategory = parseInt($("#id_target_category").val(), 10) || null;
            updateCategories(initSite, initCategory);
        }
    });
}(django.jQuery));
