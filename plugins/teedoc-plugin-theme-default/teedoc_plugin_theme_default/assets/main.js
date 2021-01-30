
(function () {
    var elements = document.getElementsByTagName("pre");
    for(var i=0; i<elements.length; ++i){
        elements[i].classList.add("language-none");
        elements[i].classList.add("line-numbers");
    }
    // $('pre').addClass("language-none");
    // $('pre').addClass("line-numbers").css("white-space", "pre-wrap");
}());

window.onload = function(){
}

$(document).ready(function(){
    $("#sidebar ul .show").slideDown(200);
    registerSidebarClick();
});

function registerSidebarClick(){
    function show_collapse_item(a_obj){
        var o_ul = a_obj.next();
        var collapsed = !o_ul.hasClass("show");
        if(collapsed){
            o_ul.slideDown(200);
            o_ul.removeClass("collapsed");
            o_ul.addClass("show");
            a_obj.children(".sub_indicator").removeClass("sub_indicator_collapsed");
        }else {
            o_ul.slideUp(200);
            o_ul.removeClass("show");
            o_ul.addClass("collapsed");
            a_obj.children(".sub_indicator").addClass("sub_indicator_collapsed");
        }
    }
    $("#sidebar ul li > a").bind("click", function(e){
        var is_click_indicator = $(e.target).hasClass("sub_indicator");
        var a_obj = $(this);
        if(a_obj.attr("href") == window.location.pathname){
            show_collapse_item(a_obj);
            return false;
        }
        show_collapse_item(a_obj);
        if(is_click_indicator){ // click indicator, only collapse, not jump to link
            return false;
        }
    });
    $("#menu").bind("click", function(e){
        if(!$("#sidebar_wrapper").is(':visible')){ // show
            $("#menu").addClass("m_menu_fixed");
            $("#menu").addClass("close");
            $("#to_top").addClass("m_hide");
            $("#sidebar_wrapper").show(100);
        }else{ // hide
            $("#menu").removeClass("m_menu_fixed");
            $("#menu").removeClass("close");
            $("#to_top").removeClass("m_hide");
            $("#sidebar_wrapper").hide(100);
        }
    });
    $("#navbar_menu_btn").bind("click", function(e){
        $("#navbar_items").toggle();
    });
    var theme = getTheme();
    setTheme(theme);
    $("#themes").bind("click", function(e){
        var theme = getTheme();
        if(theme == "light"){
            setTheme("dark");
        }else {
            setTheme("light");
        }
    });
    $("#to_top").bind("click", function(e){
        window.scrollTo({
                            top: 0, 
                            behavior: "smooth" 
                        });
        return false;
    });
}

